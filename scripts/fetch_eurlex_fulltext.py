"""批量抓取欧盟法规正文，落盘 `sources/eurlex-fulltext/`。

为什么单独成一个脚本
--------------------
正文**不能进 jsonl**：单部法规约 30~40 万字符，几部就能把产出文件撑爆。
正确做法是正文落盘、jsonl 只存路径与摘要。

为什么必须有这一步
------------------
在此之前，整个欧盟层**只有 CELEX 号与元数据，没有条文** ——
报告能列出"有哪些法规"，但无法回答"第 X 条规定了什么"。
研究者真正要引用的是条文，不是法规清单。

用法
----
    py scripts/fetch_eurlex_fulltext.py                 # 抓默认清单
    py scripts/fetch_eurlex_fulltext.py --celex 32023R1542,32024R1157
    py scripts/fetch_eurlex_fulltext.py --terms batteries,waste --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import get_connector             # noqa: E402
from app.connectors.eur_lex import FULLTEXT_DIR      # noqa: E402
from app.core.relevance import black_mass_lines      # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# 与退役电池 / 报废车 / 黑粉直接相关的欧盟核心法规。
# 这些是"要引用条文时必须打开的那几部"，不是可选项。
DEFAULT_CELEX: list[tuple[str, str]] = [
    ("32023R1542", "电池与废电池法规（现行主干法）"),
    ("32024R1157", "废物运输条例（黑粉跨境运输依据）"),
    ("32000L0053", "报废车辆指令 2000/53/EC（ELV 主干）"),
    ("52023PC0451", "报废车辆条例提案（取代指令）"),
    ("32024R1252", "关键原材料法（回收料战略价值）"),
    ("32006L0066", "旧电池指令（已被 2023/1542 取代，保留比对）"),
    ("32008L0098", "废物框架指令（废物定义的母法）"),
]


async def main() -> int:
    ap = argparse.ArgumentParser(description="批量抓取欧盟法规正文")
    ap.add_argument("--celex", default="", help="逗号分隔的 CELEX，不给则用默认清单")
    ap.add_argument("--terms", default="", help="按关键词从 SPARQL 检索后抓正文")
    ap.add_argument("--limit", type=int, default=6, help="--terms 模式下最多抓几部")
    ap.add_argument("--skip-existing", action="store_true", default=True,
                    help="已有快照的跳过（默认开）")
    ap.add_argument("--force", action="store_true", help="忽略已有快照，强制重抓")
    args = ap.parse_args()

    targets: list[tuple[str, str]] = []
    if args.celex:
        targets = [(c.strip(), "") for c in args.celex.split(",") if c.strip()]
    elif args.terms:
        async with get_connector("eur_lex") as c:
            for t in args.terms.split(","):
                t = t.strip()
                if not t:
                    continue
                try:
                    items = await c.fetch(f"keyword:{t}", since="2020-01-01",
                                          limit=args.limit)
                    print(f"  关键词「{t}」→ {len(items)} 部候选")
                    targets += [(it.meta["celex"], it.source_title or "") for it in items]
                except Exception as exc:  # noqa: BLE001
                    print(f"  ⚠️ 「{t}」检索失败：{type(exc).__name__}")
    else:
        targets = DEFAULT_CELEX

    # 去重保序（2B1：更正件 R(N) **独立抓取**——它们有真实短正文，
    # 且是独立 A2 记录；不再归一化到主体快照）
    seen: set[str] = set()
    uniq: list[tuple[str, str]] = []
    for c, note in targets:
        base = c.strip()
        if base in seen:
            continue
        seen.add(base)
        uniq.append((base, note))

    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n待抓取 {len(uniq)} 部，落盘目录 {FULLTEXT_DIR.relative_to(ROOT)}")

    ok = skip = fail = 0
    async with get_connector("eur_lex") as c:
        for celex, note in uniq:
            dest = FULLTEXT_DIR / f"{celex}.txt"
            if dest.exists() and not args.force:
                size = dest.stat().st_size
                print(f"  ⏭  {celex:<14} 已有快照（{size / 1024:.0f} KB）")
                skip += 1
                continue
            try:
                text, path = await c.fetch_fulltext(celex)
            except Exception as exc:  # noqa: BLE001
                print(f"  ❌ {celex:<14} 抓取失败：{type(exc).__name__}")
                fail += 1
                continue
            if not text or len(text) < 150:
                print(f"  ⚠️ {celex:<18} 正文过短（{len(text)} 字符），"
                      f"可能该 CELEX 无 HTML 版本（如提案/公报）")
                fail += 1
                continue
            if len(text) < 2000:
                # 2B1：短文书（更正件/决定）正文天然短——仍落盘
                print(f"  ✅ {celex:<18} {len(text):>7} 字符（短文书）→ {path.name}")
                ok += 1
                continue
            lines = black_mass_lines(text)
            tag = ("　黑粉线 " + "/".join(x[0] for x in lines)) if lines else ""
            print(f"  ✅ {celex:<14} {len(text):>7} 字符 → {path.name}{tag}")
            if note:
                print(f"       {note}")
            ok += 1

    total = len(list(FULLTEXT_DIR.glob("*.txt")))
    print(f"\n{'=' * 88}")
    print(f" 本次新增 {ok}｜跳过 {skip}｜失败 {fail}｜目录现共 {total} 部")
    print(f" → {FULLTEXT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
