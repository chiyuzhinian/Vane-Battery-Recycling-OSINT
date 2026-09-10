"""欧盟 / 美国 · 退役电池 + 报废汽车(ELV) + 黑粉 —— 政策法规采集

设计原则：**配置驱动，不硬编码关键词**。
    · 关键词体系  → sources/keyword-taxonomy-eol-battery.yaml
    · 源与访问方式 → sources/policy-eu-us-eol-blackmass.yaml
改配置即可扩展，不需要改代码。

用法
----
    py scripts/collect_policies.py                    # 欧美都采
    py scripts/collect_policies.py --region EU
    py scripts/collect_policies.py --region US
    py scripts/collect_policies.py --cluster C3_black_mass   # 只采黑粉簇
    py scripts/collect_policies.py --dry-run          # 只打印将执行的检索计划

产出
----
    outputs/eol_EU_<时间戳>.jsonl
    outputs/eol_US_<时间戳>.jsonl
    outputs/eol_summary_<时间戳>.md
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

import yaml  # noqa: E402

from app.connectors import get_connector      # noqa: E402
from app.core.relevance import judge          # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"
TAXONOMY_FILE = ROOT / "sources" / "keyword-taxonomy-eol-battery.yaml"
SOURCES_FILE = ROOT / "sources" / "policy-eu-us-eol-blackmass.yaml"

# 每个源最多取多少条（防止单源刷爆）
PER_SOURCE_LIMIT = 120


def load_config() -> tuple[dict, dict]:
    taxonomy = yaml.safe_load(TAXONOMY_FILE.read_text(encoding="utf-8")) or {}
    sources = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8")) or {}
    return taxonomy, sources


def build_plan(taxonomy: dict, sources: dict, cluster: str | None) -> dict:
    """把配置翻译成"检索计划"。

    这是这套体系的核心：**先想清楚要搜什么、去哪搜，再动手**。
    """
    clusters = taxonomy.get("clusters", [])
    if cluster:
        clusters = [c for c in clusters if c["id"] == cluster]

    # ---- EU：CELEX 精确跟踪 + 关键词发现 ----
    eu_celex = []
    for s in sources.get("eu", {}).get("sources", []):
        acc = s.get("access") or {}
        if acc.get("method") == "sparql" and acc.get("celex"):
            eu_celex.append({"celex": acc["celex"], "source_id": s["id"], "name": s.get("name")})
        for rel in (s.get("related_celex") or []):
            eu_celex.append({"celex": rel["id"], "source_id": s["id"],
                             "name": rel.get("desc", "")})

    eu_keywords: list[str] = []
    # 优先用配置里的「精选检索词」——不是所有同义词都值得搜（见 taxonomy 说明）
    for d in (taxonomy.get("discovery_terms") or []):
        t = d.get("term")
        if t and t not in eu_keywords:
            eu_keywords.append(t)
    if not eu_keywords:      # 兜底：没有精选词表时才展开全部同义词
        for c in clusters:
            for t in (c.get("terms", {}).get("en") or []):
                if t not in eu_keywords:
                    eu_keywords.append(t)

    # ---- US：机构 × 关键词（按簇配对，不做笛卡尔积爆炸）----
    fr = sources.get("us", {}).get("federal_register", {})
    us_pairs: list[tuple[str, list[str]]] = []
    agencies_map = fr.get("agencies_by_cluster", {})
    terms_map = fr.get("terms_by_cluster", {})
    for c in clusters:
        cid = c["id"]
        terms = terms_map.get(cid) or (c.get("terms", {}).get("en") or [])[:4]
        agencies = agencies_map.get(cid) or ["energy-department", "environmental-protection-agency"]
        for t in terms:
            us_pairs.append((t, agencies))

    return {
        "clusters": [c["id"] for c in clusters],
        "eu_celex": eu_celex,
        "eu_keywords": eu_keywords,
        "us_pairs": us_pairs,
    }


def print_plan(plan: dict) -> None:
    print("=" * 94)
    print(" 检索计划（由配置生成）")
    print("=" * 94)
    print(f" 关键词簇: {', '.join(plan['clusters'])}")
    print(f"\n 🇪🇺 EU —— CELEX 精确跟踪 {len(plan['eu_celex'])} 个:")
    for c in plan["eu_celex"]:
        print(f"    · {c['celex']:<14} {c['name'][:60]}")
    print(f"\n 🇪🇺 EU —— 关键词发现 {len(plan['eu_keywords'])} 个:")
    for k in plan["eu_keywords"][:14]:
        print(f"    · {k}")
    if len(plan["eu_keywords"]) > 14:
        print(f"    … 另有 {len(plan['eu_keywords']) - 14} 个")
    print(f"\n 🇺🇸 US —— 机构×关键词组合 {len(plan['us_pairs'])} 组:")
    for t, ag in plan["us_pairs"][:10]:
        print(f"    · 「{t}」 × {ag}")
    if len(plan["us_pairs"]) > 10:
        print(f"    … 另有 {len(plan['us_pairs']) - 10} 组")
    print()


# ============================================================
# 采集
# ============================================================
async def collect_eu(plan: dict, since: str) -> list:
    print(f"\n🇪🇺 欧盟 EUR-Lex SPARQL（{len(plan['eu_celex'])} 个 CELEX + {len(plan['eu_keywords'])} 个关键词）")
    items, failures = [], []
    async with get_connector("eur_lex") as conn:
        for c in plan["eu_celex"]:
            try:
                batch = await conn.fetch(f"celex:{c['celex']}", limit=PER_SOURCE_LIMIT)
                if batch:
                    for b in batch:
                        b.meta["cluster_hint"] = c["source_id"]
                print(f"  CELEX {c['celex']:<14} → {len(batch)} 条")
                items += batch
            except Exception as exc:  # noqa: BLE001
                failures.append(f"celex:{c['celex']}")
                print(f"  ⚠️ CELEX {c['celex']} 失败: {type(exc).__name__}")

        for kw in plan["eu_keywords"]:
            try:
                batch = await conn.fetch(f"keyword:{kw}", since=since, limit=PER_SOURCE_LIMIT)
                if batch:
                    print(f"  关键词「{kw}」→ {len(batch)} 条")
                items += batch
            except Exception as exc:  # noqa: BLE001
                failures.append(f"keyword:{kw}")
                print(f"  ⚠️ 关键词「{kw}」失败: {type(exc).__name__}")

    if failures:
        print(f"  ⚠️ 失败 {len(failures)} 项（SPARQL 偶发超时，可重跑补齐）")
    return _dedupe(items)


async def collect_us(plan: dict, since: str) -> list:
    print(f"\n🇺🇸 美国 Federal Register（{len(plan['us_pairs'])} 组机构×关键词）")
    items: list = []
    async with get_connector("us_federal") as conn:
        for term, agencies in plan["us_pairs"]:
            try:
                batch = await conn.fetch(terms=[term], agencies=agencies,
                                         since=since, max_pages=3, per_page=50)
                if batch:
                    print(f"  「{term[:38]}」× {len(agencies)} 机构 → {len(batch)} 条")
                items += batch
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️ 「{term[:38]}」失败: {type(exc).__name__}")
    return _dedupe(items)


def _dedupe(items: list) -> list:
    seen: set[str] = set()
    out = []
    for it in items:
        if it.evidence_id in seen:
            continue
        seen.add(it.evidence_id)
        out.append(it)
    return out


# ============================================================
# 输出
# ============================================================
def dump(items: list, path: Path, region: str) -> dict:
    kept = review = rejected = 0
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            v = judge(it.raw_text, it.source_title, scenario="policy")
            if v.relevant:
                kept += 1
                review += 1 if v.needs_human_review else 0
            else:
                rejected += 1
            f.write(json.dumps({
                "evidence_id": it.evidence_id,
                "region": region,
                "source_id": it.source_id,
                "cluster_hint": it.meta.get("cluster_hint"),
                "url": it.source_url,
                "title": it.source_title,
                "publish_date": it.publish_date.isoformat() if it.publish_date else None,
                "relevant": v.relevant,
                "relevance_score": v.score,
                "needs_human_review": v.needs_human_review,
                "hits": v.hits[:5],
                "rejected_by": v.rejected_by,
                "meta": it.meta,
                "text": it.raw_text[:1200],
            }, ensure_ascii=False) + "\n")
    print(f"  → {path.name}  总 {len(items)} | 相关 {kept}（待人工 {review}）| 拒绝 {rejected}")
    return {"total": len(items), "relevant": kept, "review": review, "rejected": rejected}


def write_summary(path: Path, stats: dict, samples: dict, plan: dict) -> None:
    lines = [
        f"# 欧美退役电池 / 报废汽车 / 黑粉 —— 政策法规采集汇总",
        "",
        f"生成时间：{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC  ",
        f"关键词簇：{', '.join(plan['clusters'])}",
        "",
        "## 采集统计",
        "",
        "| 区域 | 原始 | 相关 | 待人工复核 | 被拒 |",
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
            lines.append(f"- `{date}` **{r['title'][:120]}**")
            if r.get("url"):
                lines.append(f"  {r['url']}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  → {path.name}")


def top_n(items: list, n: int = 15) -> list[dict]:
    scored = []
    for it in items:
        v = judge(it.raw_text, it.source_title, scenario="policy")
        if v.relevant:
            scored.append({
                "title": it.source_title or "",
                "url": it.source_url,
                "publish_date": it.publish_date.isoformat() if it.publish_date else None,
                "score": v.score,
            })
    scored.sort(key=lambda r: (r["score"], r["publish_date"] or ""), reverse=True)
    return scored[:n]


async def main() -> int:
    ap = argparse.ArgumentParser(description="欧美退役电池/ELV/黑粉政策法规采集")
    ap.add_argument("--region", choices=["EU", "US", "BOTH"], default="BOTH")
    ap.add_argument("--cluster", help="只采某个关键词簇，如 C3_black_mass")
    ap.add_argument("--since", default="2023-01-01", help="起始日期（默认 2023-01-01，覆盖电池法生效后）")
    ap.add_argument("--dry-run", action="store_true", help="只打印检索计划")
    args = ap.parse_args()

    taxonomy, sources = load_config()
    plan = build_plan(taxonomy, sources, args.cluster)
    print_plan(plan)

    if args.dry_run:
        return 0

    OUT.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats: dict[str, dict] = {}
    samples: dict[str, list] = {}

    if args.region in ("EU", "BOTH"):
        items = await collect_eu(plan, args.since)
        stats["EU"] = dump(items, OUT / f"eol_EU_{stamp}.jsonl", "EU")
        samples["EU"] = top_n(items)

    if args.region in ("US", "BOTH"):
        items = await collect_us(plan, args.since)
        stats["US"] = dump(items, OUT / f"eol_US_{stamp}.jsonl", "US")
        samples["US"] = top_n(items)

    write_summary(OUT / f"eol_summary_{stamp}.md", stats, samples, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
