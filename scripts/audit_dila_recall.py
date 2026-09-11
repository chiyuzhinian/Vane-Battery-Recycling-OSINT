"""审计 DILA LEGI 增量的**全部召回**，检查判定器有没有误杀真相关内容。

背景：修复正文提取 + 补法语模式后，LEGI 召回 37 条、判定 1 条相关。
      1/37 到底是「源里确实没内容」还是「判定器还在误杀」？
      必须把 37 条**全部**看一遍才能下结论 —— 不能只看前 9 条就收工。

用法：py scripts/audit_dila_recall.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from app.connectors import get_connector                       # noqa: E402
from app.core.relevance import judge, MEMBER_STATE_PATTERNS    # noqa: E402
import re                                                      # noqa: E402

# 电池/ELV/黑粉的**核心名词**（用于在"被拒"记录里找潜在误杀）
CORE = re.compile(
    r"batterie|accumulateur|v[eé]hicule\s+hors|vhu|masse\s+noire|"
    r"broyage|broyeur|d[eé]pollution|fili[eè]re\s+rep",
    re.I)


async def main() -> None:
    async with get_connector("dila_fr") as conn:
        items = await conn.fetch(dataset="LEGI", latest=1,
                                 max_files_scanned=4000)
    print(f"LEGI 召回 {len(items)} 条\n")

    kept, suspect = [], []
    for it in items:
        v = judge(it.raw_text, it.source_title, scenario="policy")
        title = (it.source_title or "")[:88]
        if v.relevant:
            kept.append((it, v))
        else:
            # 被拒但正文含核心名词 → 可能误杀，需要人看
            if CORE.search(it.raw_text or ""):
                suspect.append((it, v))

    print(f"{'=' * 78}\n✅ 判定相关：{len(kept)} 条")
    for it, v in kept:
        print(f"  {v.score:>5.1f}  {it.source_title[:80]}")
        print(f"        {it.raw_text[:120]!r}")

    print(f"\n{'=' * 78}\n⚠️ 被拒但正文含核心名词（疑似误杀）：{len(suspect)} 条")
    for it, v in suspect:
        print(f"\n  ❌ {v.score:>5.1f}  {it.source_title[:80]}")
        # 找出正文里核心名词的上下文，判断到底是哪种
        for m in CORE.finditer(it.raw_text or ""):
            ctx = it.raw_text[max(0, m.start() - 90):m.start() + 110]
            print(f"        [{m.group(0)}] …{ctx.strip()}…")
            break

    print(f"\n{'=' * 78}\n被拒且**完全不含**核心名词：{len(items) - len(kept) - len(suspect)} 条"
          f"（这些是 déchet/recyclage 等通用词召回的噪声，拒得正确）")


if __name__ == "__main__":
    asyncio.run(main())
