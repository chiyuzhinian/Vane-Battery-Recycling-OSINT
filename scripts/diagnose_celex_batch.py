"""诊断 CELEX 批量查询失败的真实原因。

为什么要写这个
--------------
`fetch_celex_batch` 里失败分支只保留 `type(exc).__name__`：

    except Exception as exc:
        last_err = type(exc).__name__          # ← 具体消息被丢弃

于是日志里永远只有 `ConnectorError` 四个字，我们无法分辨是
**超时 / HTTP 状态 / SPARQL 语法 / Virtuoso 规划失败**。
同一个 batch（2/4/5/8/9）连续两轮采集都挂 —— 这已经是确定性行为，
不是"瞬时抖动"，必须看到真实消息才能修。

本脚本做三件事
--------------
  1. **原样重放生产分组**（chunk=4，与 `fetch_celex_batch` 一致）
  2. 打印**完整异常消息**与单批耗时
  3. 对失败的组，**逐个前缀单独查询** —— 定位是某个前缀的锅，
     还是前缀组合的锅（REGEX 交替越长，Virtuoso 规划越慢）

用法
----
    py scripts/diagnose_celex_batch.py
    py scripts/diagnose_celex_batch.py --chunk 4 --only 2   # 只测第 2 组
"""
from __future__ import annotations

import re
import sys
import time
import asyncio
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.connectors import get_connector  # noqa: E402
from app.connectors.eur_lex import Q_CELEX_BATCH  # noqa: E402


def load_prefixes() -> list[str]:
    p = ROOT / "sources" / "eu-acts-tracked.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    out: list[str] = []
    for a in (d.get("tracked") or []):
        if isinstance(a, dict):
            c = a.get("celex")
            if c:
                out.append(str(c))
    return out


async def query(conn, pattern: str, limit: int = 1500) -> tuple[int, float]:
    t0 = time.monotonic()
    rows = await conn._sparql(
        Q_CELEX_BATCH.format(pattern=pattern, limit=limit))
    return len(rows), time.monotonic() - t0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=4)
    ap.add_argument("--only", type=int, default=0,
                    help="只测第 N 组（0=全部）")
    ap.add_argument("--via-fetch", action="store_true",
                    help="走生产代码 fetch_celex_batch（用于验证修复是否生效）")
    args = ap.parse_args()

    prefixes = load_prefixes()
    groups = [prefixes[i:i + args.chunk]
              for i in range(0, len(prefixes), args.chunk)]
    print(f"前缀 {len(prefixes)} 个 → {len(groups)} 组（chunk={args.chunk}）\n")

    # ---- 验证模式：完整走生产路径，看修复是否真的让失败的批次都能取到 ----
    if args.via_fetch:
        subset = groups[args.only - 1] if args.only else prefixes
        print(f"送到 fetch_celex_batch 的前缀：{subset}\n")
        async with get_connector("eur_lex") as conn:
            t0 = time.monotonic()
            out = await conn.fetch_celex_batch(subset)
            dt = time.monotonic() - t0
        print(f"\nfetch_celex_batch → {len(out)} 条 / {dt:.1f}s")
        got = {str(it.meta.get("celex") or "").split("R(")[0]
               for it in out if getattr(it, "meta", None)}
        want = {p.split("R(")[0] for p in subset}
        miss = sorted(want - got)
        if miss:
            print(f"⚠️ 仍缺 {len(miss)} 个：{miss[:10]}")
            return 1
        print("✅ 全部前缀都有对应记录 —— 修复生效")
        return 0

    bad_groups = 0
    async with get_connector("eur_lex") as conn:
        for idx, g in enumerate(groups, 1):
            if args.only and idx != args.only:
                continue
            pattern = "|".join(re.escape(p) for p in g)
            try:
                n, dt = await query(conn, pattern)
                print(f"  组 {idx:>2} {g[0]:<18} ✅ {n:>5} 行  {dt:6.1f}s")
            except Exception as exc:  # noqa: BLE001
                bad_groups += 1
                print(f"  组 {idx:>2} {g[0]:<18} ❌ {type(exc).__name__}: "
                      f"{str(exc)[:220]}")
                # ---- 逐个前缀定位 ----
                for p in g:
                    try:
                        n, dt = await query(conn, re.escape(p))
                        print(f"        └ 单独 {p:<18} ✅ {n:>4} 行 {dt:6.1f}s")
                    except Exception as e2:  # noqa: BLE001
                        print(f"        └ 单独 {p:<18} ❌ "
                              f"{type(e2).__name__}: {str(e2)[:180]}")

    print()
    if bad_groups:
        print(f"⚠️ {bad_groups} 组失败 —— 真实原因见上方消息")
        return 1
    print("✅ 全部分组成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
