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
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from app.connectors import get_connector               # noqa: E402
from app.connectors.base import RawEvidence            # noqa: E402
from app.core.relevance import RelevanceVerdict, judge  # noqa: E402
from app.core.relevance_browser import judge_browser    # noqa: E402

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


# ============================================================
# 欧盟成员国层（德国 / 法国）—— 走官方结构化通道，不爬页面
# ------------------------------------------------------------
# ⭐ 这一层的价值：欧盟法规告诉你"要求是什么"，成员国数据告诉你"实际做到多少"。
#    实测两个通道都是**官方结构化数据**，比网页抓取可靠得多：
#      de_gesetze 德国联邦法律门户 XML  → 6130 部法规，正文带修订历史
#      datafair   法国 ADEME Data Fair   → 122 条/集，按省分的破碎厂与报废车量
# ============================================================
async def collect_member_states() -> list:
    items: list = []

    print("\n🇩🇪 德国联邦法律（官方 XML）")
    try:
        async with get_connector("de_gesetze") as conn:
            batch = await conn.fetch(slugs=[
                "altautov",       # AltfahrzeugV 报废车法（转化 ELV 指令）
                "battdg",         # BattDG 电池法（实施 EU 2023/1542）
                "avv",            # AVV 欧洲废物目录（危废分类 → 黑粉定性）
                "eag-behandv",    # 废弃电子电气设备处理要求
            ])
            for it in batch:
                hits = it.meta.get("term_hits") or {}
                print(f"  {it.meta['slug']:<14} {len(it.raw_text):>7} 字符"
                      f" | 术语命中 {list(hits)[:4]}")
            items += batch
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️ 德国法规失败: {type(exc).__name__}")

    print("\n🇫🇷 法国 ADEME 开放数据（Data Fair API）")
    try:
        async with get_connector("datafair") as conn:
            batch = await conn.fetch(ids=list(
                get_connector("datafair").DEFAULT_DATASETS))
            for it in batch:
                print(f"  {it.meta['dataset_id'][:56]:<58}"
                      f" 记录 {it.meta['rows_total']}")
            items += batch
    except Exception as exc:  # noqa: BLE001
        print(f"  ⚠️ 法国 ADEME 失败: {type(exc).__name__}")

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
# 浏览器捕获通道接入
# ------------------------------------------------------------
# 背景：PHMSA / CalRecycle / BCI / ECHA / ADEME 等站点直连被拦（403），
#       但走浏览器可得（见 scripts/collect_browser_sources.py）。
#       它们产出在 outputs/browser_*.jsonl，需并入主采集管线。
#
# ⭐ 关键：**不能重新用政策规则判定**。
#    浏览器抓的是整页渲染文本，全局导航会带来大量同母类噪声
#    （实测 CalRecycle `/epr/` 把纺织/包装产品线都判成了相关）。
#    它们的判定已在抓取时用 judge_browser 完成，这里必须**沿用**，
#    否则一进主管线就把噪声重新引回来。
# ============================================================
# 向后兼容：region 字段是 2026-09-11 才加进浏览器记录的。
# 旧 jsonl 没有该字段 → 回退查这张表（与 collect_browser_sources.SITES 保持一致）。
# 新增被拦站点时**必须两处都加**，否则区域会归错。
_BROWSER_REGION_FALLBACK = {
    "phmsa": "US", "calrecycle": "US", "bci": "US", "call2recycle": "US",
    "echa": "EU", "france": "EU-MemberState",
}


def load_browser_evidence() -> list:
    """把 outputs/browser_*.jsonl 转成统一的 RawEvidence。"""
    files = sorted(OUT.glob("browser_*.jsonl"))
    if not files:
        return []
    out, seen = [], set()
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = hashlib.sha1((r.get("url") or "").encode("utf-8")).hexdigest()[:16]
            if eid in seen:
                continue
            seen.add(eid)
            sid = r.get("source_id") or "browser_capture"
            region = (r.get("region")
                      or _BROWSER_REGION_FALLBACK.get(sid.replace("browser_", ""))
                      or "EU")
            out.append(RawEvidence(
                evidence_id=eid,
                channel="browser_capture",
                source_id=sid,
                source_url=r.get("url"),
                source_title=r.get("title"),
                publish_date=None,
                raw_text=r.get("text") or "",
                meta={
                    "region": region,
                    "cluster_hint": r.get("cluster"),
                    "publish_date_hint": r.get("publish_date_hint"),
                    # ⭐ 声明判定场景，让 dump()/top_n() 用 judge_browser 而不是政策规则
                    "relevance_scenario": "browser",
                    "rejected_by": r.get("rejected_by"),
                    "full_text_path": r.get("full_text_path"),
                    "text_len_full": r.get("text_len_full"),
                },
            ))
    return out


# ============================================================
# 输出
# ============================================================
def _judge_evidence(it) -> "RelevanceVerdict":
    """按证据自己声明的场景选判定规则。

    为什么不能一律用政策规则：浏览器通道抓的是整页渲染文本，
    全局导航会让政策规则产生大量同母类假阳性（实测 CalRecycle）。
    """
    if it.meta.get("relevance_scenario") == "browser":
        return judge_browser(it.source_title or "", it.source_url or "", it.raw_text)
    return judge(it.raw_text, it.source_title, scenario="policy")


def dump(items: list, path: Path, region: str) -> dict:
    kept = review = rejected = 0
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            v = _judge_evidence(it)
            if v.relevant:
                kept += 1
                review += 1 if v.needs_human_review else 0
            else:
                rejected += 1
            f.write(json.dumps({
                "evidence_id": it.evidence_id,
                "region": region,
                "channel": it.channel,
                "source_id": it.source_id,
                "cluster_hint": it.meta.get("cluster_hint"),
                "url": it.source_url,
                "title": it.source_title,
                "publish_date": it.publish_date.isoformat() if it.publish_date else None,
                "publish_date_hint": it.meta.get("publish_date_hint"),
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
        v = _judge_evidence(it)
        if v.relevant:
            scored.append({
                "title": it.source_title or "",
                "url": it.source_url,
                "publish_date": (it.publish_date.isoformat() if it.publish_date
                                 else (it.meta.get("publish_date_hint") or None)),
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
    ap.add_argument("--include-browser", action="store_true",
                    help="并入浏览器捕获的被拦站点（PHMSA/CalRecycle/BCI/ECHA/ADEME）")
    ap.add_argument("--no-member-states", action="store_true",
                    help="跳过欧盟成员国层（德国法规 XML + 法国 ADEME API）")
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

    # 浏览器捕获通道（按证据自带的 region 分配到对应区域）
    # 用前缀匹配而不是精确匹配：region 有 "EU" / "EU-MemberState" / "US" /
    # "US/State-Local" 等层级写法，精确匹配会漏。
    browser_by_region: dict[str, list] = {"EU": [], "US": []}
    if args.include_browser:
        br = load_browser_evidence()
        for it in br:
            reg = (it.meta.get("region") or "EU").upper()
            bucket = "US" if reg.startswith("US") else "EU"
            browser_by_region[bucket].append(it)
        print(f"\n 浏览器捕获通道并入 {len(br)} 条："
              + " ｜ ".join(f"{k} {len(v)}" for k, v in browser_by_region.items() if v))

    if args.region in ("EU", "BOTH"):
        items = await collect_eu(plan, args.since)
        if not args.no_member_states:
            items += await collect_member_states()
        items += browser_by_region.get("EU", [])
        stats["EU"] = dump(items, OUT / f"eol_EU_{stamp}.jsonl", "EU")
        samples["EU"] = top_n(items)

    if args.region in ("US", "BOTH"):
        items = await collect_us(plan, args.since)
        items += browser_by_region.get("US", [])
        stats["US"] = dump(items, OUT / f"eol_US_{stamp}.jsonl", "US")
        samples["US"] = top_n(items)

    write_summary(OUT / f"eol_summary_{stamp}.md", stats, samples, plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
