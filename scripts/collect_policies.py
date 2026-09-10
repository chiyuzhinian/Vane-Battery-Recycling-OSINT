"""欧美政策全量采集脚本 —— 把"能连上"变成"拿到完整政策清单"。

用法
----
    py scripts/collect_policies.py                # 欧美都采
    py scripts/collect_policies.py --region US    # 只采美国
    py scripts/collect_policies.py --region EU    # 只采欧盟
    py scripts/collect_policies.py --since 2024-01-01

产出
----
    outputs/policy_US_<时间戳>.jsonl      逐条政策
    outputs/policy_EU_<时间戳>.jsonl
    outputs/policy_summary_<时间戳>.md    人类可读汇总（含 TOP 条目）

设计说明
--------
· 美国：Federal Register 公开 API，按「关键词 × 机构」笛卡尔积翻页，
        覆盖 DOE / EPA / IRS / DOT / FERC。
· 欧盟：走 Publications Office SPARQL，双路并行——
        路径 A「CELEX 精确跟踪」：已知主干法规 + 其更正版本；
        路径 B「关键词发现」：按标题关键词发现新立法（仅英文）。
        另外拉取主干法规的**修订/废止/合并版本关系图**。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import get_connector          # noqa: E402
from app.core.relevance import judge              # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"

# ---------- 美国采集配置 ----------
US_AGENCIES = [
    "energy-department",
    "environmental-protection-agency",
    "internal-revenue-service",
    "transportation-department",          # 退役电池属于危险货物，运输规则归它管
]

US_TERMS = [
    "battery recycling",
    "lithium-ion battery",
    "battery material",
    "critical minerals",
    "battery manufacturing",
    "electric vehicle battery",
]

# ---------- 欧盟采集配置 ----------
# 路径 A：精确跟踪的 CELEX（前缀匹配）
EU_CELEX_PREFIXES = [
    "32023R1542",     # 电池与废电池法规（主干）
    "32006L0066",     # 旧电池指令（已被新法规取代，需追踪其废止过程）
    "32000L0053",     # 报废车辆指令（ELV，影响电池回收渠道）
]

# 路径 B：关键词发现
EU_KEYWORDS = [
    "battery",
    "batteries",
    "waste batteries",
    "recycled content",
    "critical raw materials",
    "end-of-life vehicles",
    "ecodesign",
]


def _dump(items: list, path: Path, region: str) -> dict[str, int]:
    kept = rejected = review = 0
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            v = judge(it.raw_text, it.source_title)
            if v.relevant:
                kept += 1
                if v.needs_human_review:
                    review += 1
            else:
                rejected += 1
            f.write(json.dumps({
                "evidence_id": it.evidence_id,
                "region": region,
                "source_id": it.source_id,
                "url": it.source_url,
                "title": it.source_title,
                "publish_date": it.publish_date.isoformat() if it.publish_date else None,
                "relevant": v.relevant,
                "relevance_score": v.score,
                "needs_human_review": v.needs_human_review,
                "review_reason": v.review_reason,
                "rejected_by": v.rejected_by,
                "meta": it.meta,
                "text": it.raw_text[:1200],
            }, ensure_ascii=False) + "\n")
    print(f"  → {path.name}  相关 {kept}（其中待人工 {review}）/ 拒绝 {rejected}")
    return {"total": len(items), "relevant": kept, "review": review, "rejected": rejected}


async def collect_us(since: str, max_pages: int) -> tuple[list, dict]:
    print(f"\n🇺🇸 美国 Federal Register（{len(US_TERMS)} 关键词 × {len(US_AGENCIES)} 机构，since={since}）")
    async with get_connector("us_federal") as conn:
        items = await conn.fetch(
            terms=US_TERMS, agencies=US_AGENCIES,
            since=since, max_pages=max_pages, per_page=50,
        )
    print(f"  取回 {len(items)} 条")
    return items, {}


async def collect_eu(since: str, max_pages: int) -> tuple[list, dict]:
    print(f"\n🇪🇺 欧盟 EUR-Lex SPARQL（CELEX 跟踪 {len(EU_CELEX_PREFIXES)} 组 + 关键词 {len(EU_KEYWORDS)} 个）")
    items: list = []
    relations: dict = {}
    failures: list[str] = []
    async with get_connector("eur_lex") as conn:
        # 路径 A：CELEX 精确跟踪
        for prefix in EU_CELEX_PREFIXES:
            try:
                batch = await conn.fetch(f"celex:{prefix}", limit=100)
                print(f"  CELEX {prefix}: {len(batch)} 条")
                items += batch
            except Exception as exc:  # noqa: BLE001
                # 单条查询失败不应中断整轮采集（SPARQL 端偶发超时是常态）
                failures.append(f"celex:{prefix} {type(exc).__name__}")
                print(f"  ⚠️ CELEX {prefix} 失败: {type(exc).__name__}")

        # 路径 B：关键词发现（只留英文）
        for kw in EU_KEYWORDS:
            try:
                batch = await conn.fetch(f"keyword:{kw}", since=since, limit=100)
                print(f"  关键词「{kw}」: {len(batch)} 条")
                items += batch
            except Exception as exc:  # noqa: BLE001
                failures.append(f"keyword:{kw} {type(exc).__name__}")
                print(f"  ⚠️ 关键词「{kw}」失败: {type(exc).__name__}")

        # 关系图：主干法规的修订 / 废止 / 合并版本
        main_work = next(
            (i.source_url for i in items if i.meta.get("celex") == "32023R1542"), None
        )
        if main_work:
            try:
                relations = await conn.fetch_relations(main_work)
                print(f"  关系图: {[f'{k}({len(v)})' for k, v in relations.items()]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  关系图拉取失败: {exc}")

    if failures:
        print(f"  ⚠️ 本轮失败 {len(failures)} 项，可重跑补齐: {failures}")

    # 去重（同一 CELEX 可能被路径 A/B 同时命中）
    seen: set[str] = set()
    uniq = []
    for it in items:
        if it.evidence_id in seen:
            continue
        seen.add(it.evidence_id)
        uniq.append(it)
    print(f"  去重后 {len(uniq)} 条")
    return uniq, relations


def write_summary(path: Path, stats: dict, samples: dict) -> None:
    lines = [
        f"# 欧美政策采集汇总 · {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
        "",
        "## 采集统计",
        "",
        "| 区域 | 原始条数 | 相关 | 待人工复核 | 被拒 |",
        "|---|---|---|---|---|",
    ]
    for region, s in stats.items():
        lines.append(f"| {region} | {s['total']} | **{s['relevant']}** | {s['review']} | {s['rejected']} |")
    lines += ["", "## 相关性最高的条目", ""]
    for region, rows in samples.items():
        lines.append(f"### {region}")
        lines.append("")
        for r in rows:
            date = (r.get("publish_date") or "")[:10]
            lines.append(f"- `{date}` **{r['title'][:110]}**  ")
            lines.append(f"  {r.get('url') or ''}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  → 汇总报告 {path.name}")


async def main() -> int:
    ap = argparse.ArgumentParser(description="欧美政策全量采集")
    ap.add_argument("--region", choices=["US", "EU", "BOTH"], default="BOTH")
    ap.add_argument("--since", default="2024-01-01", help="起始日期（默认 2024-01-01）")
    ap.add_argument("--max-pages", type=int, default=5)
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats: dict[str, dict] = {}
    samples: dict[str, list] = {}

    if args.region in ("US", "BOTH"):
        items, _ = await collect_us(args.since, args.max_pages)
        stats["US"] = _dump(items, OUT / f"policy_US_{stamp}.jsonl", "US")
        samples["US"] = _top(items)

    if args.region in ("EU", "BOTH"):
        items, relations = await collect_eu(args.since, args.max_pages)
        stats["EU"] = _dump(items, OUT / f"policy_EU_{stamp}.jsonl", "EU")
        samples["EU"] = _top(items)
        if relations:
            (OUT / f"policy_EU_relations_{stamp}.json").write_text(
                json.dumps(relations, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  → 关系图 policy_EU_relations_{stamp}.json")

    write_summary(OUT / f"policy_summary_{stamp}.md", stats, samples)
    return 0


def _top(items: list, n: int = 12) -> list[dict]:
    scored = []
    for it in items:
        v = judge(it.raw_text, it.source_title)
        if v.relevant:
            scored.append({
                "title": it.source_title or "",
                "url": it.source_url,
                "publish_date": it.publish_date.isoformat() if it.publish_date else None,
                "score": v.score,
            })
    scored.sort(key=lambda r: (r["score"], r["publish_date"] or ""), reverse=True)
    return scored[:n]


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
