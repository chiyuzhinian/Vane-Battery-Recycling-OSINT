"""验证 DILA 正文提取修复：同一份增量包，修复前后判定结果对比。

修复前：raw_text 前 4000 字符被 <META> 机器字段霸占
        → 8 条落盘记录**全部**判为不相关（分数 0.0）
修复后：raw_text 是 <BLOC_TEXTUEL> 里的条文正文

用法：py scripts/verify_dila_fix.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from app.connectors import get_connector          # noqa: E402
from app.core.relevance import judge              # noqa: E402


async def main() -> None:
    async with get_connector("dila_fr") as conn:
        for dataset in ("JORF", "LEGI"):
            print(f"\n{'=' * 76}\n📦 {dataset}")
            try:
                items = await conn.fetch(dataset=dataset, latest=1,
                                         max_files_scanned=1200)
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️ 失败: {type(exc).__name__}: {exc}")
                continue

            if not items:
                print("  （无命中）")
                continue

            kept = 0
            for it in items:
                v = judge(it.raw_text, it.source_title, scenario="policy")
                kept += 1 if v.relevant else 0
                mark = "✅" if v.relevant else "❌"
                body = it.meta.get("body_chars", 0)
                print(f"  {mark} {v.score:>5.1f}  正文{body:>7,}字  "
                      f"命中{it.meta.get('matched_terms')}")
                print(f"      {it.source_title[:96]}")
                print(f"      正文头: {it.raw_text[:110]!r}")
            print(f"\n  → {len(items)} 条，相关 {kept} 条"
                  f"（修复前同批为 0 条相关）")


if __name__ == "__main__":
    asyncio.run(main())
