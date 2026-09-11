"""收敛闸门的单元测试 —— 直接跑：py tests/test_convergence_gates.py

为什么必须有这些测试
--------------------
收敛判据是**防死循环的最后一道闸门**。它一旦失灵，系统会：
  · 给已经饱和的源持续加权（越跑越依赖老源）
  · 永远不判定收敛（无限循环）

而收敛判据曾经真的坏过（2026-09-10）：用的是累积比率而非本轮边际，
导致阈值 2% 永远触发不了。这类 bug 不会报错、不会崩溃，
只会让报告看起来"一切正常"——所以必须有断言兜住。

最关键的两条：
  A. 「抓不到数据」绝不能等于「没有新数据」
     —— API 故障返回 0 条时，边际率算出来是 0%，会被误判成"已收敛"，
        于是系统高高兴兴地停下来，而实际上是采集失败了。
  B. 小样本轮不能计入收敛连击
     —— 同理：只抓到 5 条且都是旧的，不能证明"饱和"。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core import feedback as F  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def _engine(tmp: str) -> "F.FeedbackEngine":
    return F.FeedbackEngine(Path(tmp), known_keywords=["batteries"],
                            known_sources=["src"])


def _records(n: int, src: str = "src", kw: str = "batteries") -> list[dict]:
    """n 条记录。evidence_id 相同 → 第二次喂进去时会被判为"不新"。"""
    return [{
        "source_id": src, "keyword": kw,
        "evidence_id": f"{src}-{kw}-{i}",
        "relevant": True,
        "title": "battery recycling",
        "text": "battery recycling cathode black mass " * 20,
    } for i in range(n)]


def case_a_zero_yield() -> bool:
    """整轮 0 条 → 必须报「源故障」，绝不能收敛。"""
    with tempfile.TemporaryDirectory() as t:
        r = _engine(t).analyze(1)
    ok = (not r.converged) and "故障" in r.reason
    print(f"  A 零产出轮           → converged={r.converged} streak={r.streak}")
    print(f"     reason: {r.reason}")
    return ok


def case_b_small_sample() -> bool:
    """样本量不足的轮不计入收敛连击（5 条 << 门槛 30）。"""
    with tempfile.TemporaryDirectory() as t:
        e = _engine(t)
        e.observe(_records(5), 1)
        r1 = e.analyze(1)
        e.observe(_records(5), 2)
        r2 = e.analyze(2)
    ok = (r1.streak == 0 and r2.streak == 0) and not r2.converged
    print(f"  B 小样本连续两轮(各5) → r1.streak={r1.streak} r2.streak={r2.streak} "
          f"converged={r2.converged}")
    return ok


def case_c_natural_convergence() -> bool:
    """样本充足 + 连续两轮零边际 → 自然收敛（不靠硬上限兜底）。"""
    with tempfile.TemporaryDirectory() as t:
        e = _engine(t)
        e.observe(_records(50), 1)
        r1 = e.analyze(1)          # 首轮全新 → 边际 100%
        e.observe(_records(50), 2)
        r2 = e.analyze(2)          # 重复 → 边际 0%，连击 1
        e.observe(_records(50), 3)
        r3 = e.analyze(3)          # 重复 → 边际 0%，连击 2 → 收敛
    ok = (r1.streak == 0 and r2.streak == 1 and r3.streak >= 2
          and r3.converged and "自然收敛" in r3.reason)
    print(f"  C 饱和序列(各50条)    → 边际 {r1.novel_rate:.0%}/"
          f"{r2.novel_rate:.0%}/{r3.novel_rate:.0%}  连击 {r1.streak}/"
          f"{r2.streak}/{r3.streak}")
    print(f"     r3.converged={r3.converged}  reason: {r3.reason}")
    return ok


def case_d_marginal_not_cumulative() -> bool:
    """回归测试：确保不会退回到「累积比率」。

    累积比率在饱和后仍会显示高位（旧分子 ÷ 膨胀的分母），
    第 3 轮会显示 ~33% 而不是 0%。
    """
    with tempfile.TemporaryDirectory() as t:
        e = _engine(t)
        for rnd in (1, 2, 3):
            e.observe(_records(50), rnd)
            r = e.analyze(rnd)
        # 累积口径会得到 50/150 = 33%，本轮口径应为 0%
        ok = r.novel_rate < 0.02
    print(f"  D 第3轮边际口径        → 本轮 {r.novel_rate:.1%}（累积口径会显示 33%）")
    return ok


def main() -> int:
    print("收敛闸门单元测试")
    print("=" * 84)
    results = [
        ("A 零产出=源故障，非收敛", case_a_zero_yield()),
        ("B 小样本轮不计入连击", case_b_small_sample()),
        ("C 样本充足时自然收敛", case_c_natural_convergence()),
        ("D 用本轮边际而非累积比率", case_d_marginal_not_cumulative()),
    ]
    print("-" * 84)
    for label, ok in results:
        print(f"  {'✅' if ok else '❌'} {label}")
    passed = sum(1 for _, ok in results if ok)
    print(f"\n  通过 {passed}/{len(results)}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
