"""证据端到端校验：采集 → 判定 → 黑粉分线。

回答的问题
----------
冒烟测试只证明"能拿到字节"，不证明"能被系统接受"。
本项目踩过最危险的坑正是这一条：

    德国 AltfahrzeugV / AVV、法国 ADEME REP-VHU  —— 数据采到了，
    但判定层不认（未命中必修词）→ 整层静默不入库。

所以本脚本对每条证据跑**真实的判定链**：
    app.core.relevance.judge_policy   → relevant / score / needs_human_review
    app.core.relevance.black_mass_lines → 命中的黑粉监管线

用法
----
    py scripts/verify_evidence.py nl_bwb
    py scripts/verify_evidence.py es_boe --limit 6
    py scripts/verify_evidence.py de_gesetze nl_bwb es_boe dila_fr
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import REGISTRY, get_connector  # noqa: E402
from app.core.relevance import black_mass_lines, judge_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


async def check(key: str, limit: int) -> tuple[int, int]:
    conn = get_connector(key)
    print("=" * 76)
    print(f"连接器 {key}（{type(conn).__name__}）")
    print("=" * 76)

    try:
        items = await conn.fetch(limit=limit)
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ 采集失败：{type(exc).__name__}: {exc}")
        return 0, 0

    accepted = 0
    for it in items:
        text = it.raw_text or ""
        v = judge_policy(text, it.source_title or "")
        rel = bool(getattr(v, "relevant", False))
        accepted += rel
        lines = black_mass_lines(text, it.source_title or "")
        flag = "✅" if rel else "❌"
        review = "🟡待人工复核" if getattr(v, "needs_human_review", False) else ""
        print(f"\n  {flag} {it.source_title}")
        print(f"      正文 {len(text):>7} 字符 | score={getattr(v, 'score', '?')} "
              f"| 命中 {getattr(v, 'hits', [])[:3]} {review}")
        if not rel:
            print(f"      ⚠️ 被判不相关：rejected_by={getattr(v, 'rejected_by', None)}"
                  f"  ← **此条会静默不入库**")
        if lines:
            print(f"      黑粉线：{'、'.join(lines)}")
        print(f"      头部：{text[:110].replace(chr(10), ' ')}")

    print(f"\n  → 采集 {len(items)} 条，判定通过 {accepted}/{len(items)}")
    return len(items), accepted


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+", help="连接器 key")
    ap.add_argument("--limit", type=int, default=5)
    args = ap.parse_args()

    bad = [k for k in args.keys if k not in REGISTRY]
    if bad:
        print(f"未知连接器 {bad}；可用：{sorted(REGISTRY)}")
        return 2

    total = acc = 0
    for k in args.keys:
        n, a = await check(k, args.limit)
        total += n
        acc += a
        print()
    print("=" * 76)
    print(f"合计：采集 {total} 条，判定通过 {acc} 条"
          f"（{acc / total * 100:.0f}%）" if total else "合计：无数据")
    return 0 if total and acc == total else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
