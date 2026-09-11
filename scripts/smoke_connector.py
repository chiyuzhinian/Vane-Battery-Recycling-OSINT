"""通用连接器冒烟测试：probe + 真实 fetch，打印可核对的证据。

用法
----
    py scripts/smoke_connector.py nl_bwb
    py scripts/smoke_connector.py nl_bwb --fetch --limit 6
    py scripts/smoke_connector.py                  # 全部连接器只 probe
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import REGISTRY, get_connector  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


async def run(key: str, do_fetch: bool, limit: int, terms: list[str]) -> None:
    conn = get_connector(key)
    print("=" * 74)
    print(f"连接器 {key}  ({type(conn).__name__})")
    print("=" * 74)

    probe = await conn.probe()
    print(f"probe: {probe}")
    for s in probe.sample:
        print(f"    · {s}")

    if not do_fetch:
        return

    print()
    kwargs = {"limit": limit}
    if terms:
        kwargs["terms"] = terms
    items = await conn.fetch(**kwargs)
    print(f"fetch 返回 {len(items)} 条")
    total = 0
    for it in items:
        text = it.raw_text or ""
        total += len(text)
        meta = it.meta or {}
        extra = {k: meta[k] for k in
                 ("bwb_id", "version_start", "version_count", "law_type", "rechtsgebied")
                 if k in meta}
        print(f"  · {it.source_title}")
        print(f"      {len(text):>7} 字符  date={it.publish_date}  {extra}")
        if meta.get("term_hits"):
            print(f"      术语命中: {meta['term_hits']}")
        print(f"      url: {it.source_url}")
        print(f"      正文头部: {text[:150].replace(chr(10), ' ')}")
    if items:
        print(f"\n合计正文 {total} 字符，平均 {total // len(items)} 字符/条")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key", nargs="?", help="连接器 key；省略则全部 probe")
    ap.add_argument("--fetch", action="store_true", help="真实拉取")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--terms", nargs="*", default=None)
    args = ap.parse_args()

    keys = [args.key] if args.key else list(REGISTRY)
    if args.key and args.key not in REGISTRY:
        print(f"未知连接器 {args.key}；可用：{list(REGISTRY)}")
        raise SystemExit(2)

    async def _all() -> None:
        for k in keys:
            try:
                await run(k, args.fetch if args.key else False, args.limit, args.terms or [])
            except Exception as exc:  # noqa: BLE001
                print(f"  ❌ {k}: {type(exc).__name__}: {exc}")
            print()

    asyncio.run(_all())


if __name__ == "__main__":
    main()
