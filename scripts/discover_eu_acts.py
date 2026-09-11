"""欧盟层扩充：找出所有「以核心法为依据」的法案（授权/实施/修订/提案）。

为什么这是欧盟层最大的缺口
--------------------------
主采集计划里只**精确跟踪 5 部法**（电池法 / 报废车指令 / 报废车提案 /
废物运输条例 / 关键原材料法）。但：

    · 电池法 (EU) 2023/1542 是**框架法**——真正落地义务的是它的
      授权法案与实施法案：碳足迹计算方法、再生料含量核算、尽职调查、
      电池护照、回收效率……这些**一部都没被跟踪**。
    · 结果是"知道有法规，不知道具体要做什么"。

怎么找
------
这类法案的标题里**必然写明**所依据的基础法号，例如：
    "Commission Delegated Regulation (EU) 2025/606 supplementing
     Regulation (EU) 2023/1542 ..."
所以按标题锚点字符串检索最稳（且已在连接器里排除了全表扫描的写法）。

⚠️ 慢：单次查询实测 20~60 秒（冷启动更慢），6 个锚点×2 个 sector 约需 5 分钟。
   这是 Virtuoso 端的问题，不是网络问题——端点本身 1 秒就答。

用法
----
    py scripts/discover_eu_acts.py
    py scripts/discover_eu_acts.py --emit sources/eu-acts-suggestion.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import get_connector  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# 核心法 → 标题锚点
ANCHORS: list[tuple[str, str, str]] = [
    ("32023R1542", "2023/1542", "电池与废电池法规"),
    ("32000L0053", "2000/53/EC", "报废车（ELV）指令"),
    ("32024R1157", "2024/1157", "废物运输条例"),
    ("32024R1252", "2024/1252", "关键原材料法"),
    ("32006L0066", "2006/66/EC", "旧电池指令"),
    ("32008L0098", "2008/98/EC", "废物框架指令"),
]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", default="20(1[8-9]|2[0-9])",
                    help="CELEX 年份正则片段（默认 2018-2029）")
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--emit", default="", help="把候选写到此 YAML 文件")
    args = ap.parse_args()

    conn = get_connector("eur_lex")
    found: dict[str, list[dict]] = {}

    for base_celex, anchor, label in ANCHORS:
        print("=" * 92)
        print(f"锚点 {anchor:<12} （{base_celex} {label}）")
        print("=" * 92)
        try:
            acts = await conn.find_acts_by_title(anchor, args.years, args.limit)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ 查询失败：{type(exc).__name__}: {exc}")
            print()
            continue

        acts = [a for a in acts if a["celex"] != base_celex]
        found[base_celex] = acts
        kinds = Counter(a["sector"] for a in acts)
        print(f"  命中 {len(acts)} 个；类型分布 {dict(kinds)}")
        for a in sorted(acts, key=lambda x: x["celex"]):
            marker = "📜" if a["celex"].startswith("3") else "💡"
            date = (a["date"] or "")[:10]
            print(f"    {marker} {a['celex']:<16} {date:<11} {a['title'][:88]}")
        print()

    total = sum(len(v) for v in found.values())
    print("=" * 92)
    print(f"合计候选 {total} 个（📜=已生效立法  💡=提案）")

    if args.emit and total:
        lines = ["# 由 scripts/discover_eu_acts.py 自动生成 —— 供人工筛选后并入主配置",
                 "# 每个条目含：CELEX / 类型 / 日期 / 标题", "", "candidates:"]
        for base, acts in found.items():
            if not acts:
                continue
            lines.append(f"  # ── 依据 {base} ──")
            for a in sorted(acts, key=lambda x: x["celex"]):
                title = (a["title"] or "").replace('"', "'")[:150]
                lines.append(f'  - celex: "{a["celex"]}"')
                lines.append(f'    base: "{base}"')
                lines.append(f'    kind: "{a["sector"]}"')
                lines.append(f'    date: "{a["date"][:10] if a["date"] else ""}"')
                lines.append(f'    title: "{title}"')
        path = Path(args.emit)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"→ 已写出 {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
