"""数据源发现器 —— 回答「这类数据该去哪找」。

为什么需要它
------------
关键词不是拿来搜网页的，是**拿来定位源的**。但"去哪找"这件事本身
有很强的规律：绝大多数政府/机构开放数据都跑在**少数几个平台软件**上，
而每个平台都有自己的 API。识别出平台 = 绕过整站爬取。

实测例子（2026-09-11，法国 ADEME）：
    网页抓取 → 0 条相关（标题是"Economie circulaire et déchets"这种分类名，
               既没电池词也没车辆词，看起来毫无价值）
    识别平台 → 发现 data.ademe.fr 跑的是 **Data Fair** → 调它的 API
     → 立刻拿到 9 个 REP-VHU 数据集：
         REP - VHU - Tonnages collectés Broyeurs depuis 2018   （破碎厂吨位 ⭐黑粉上游）
         REP - VHU - TRR et TRV des CVHU depuis 2018           （回收率指标）
         REP - VHU - Liste des producteurs enregistrés SYDEREP （生产者名录）

    **同一个站，换个入口，价值天差地别。**

支持的平台
----------
    datafair    Data Fair   —— data.ademe.fr 等
    ckan        CKAN        —— data.gov / data.gov.uk / 大量国家门户
    socrata     Socrata     —— 美国州/市级（加州等）
    ods         OpenDataSoft—— 法国/欧盟部分门户
    datagouv    data.gouv.fr 自有 API

用法
----
    py scripts/discover_sources.py --q "vhu,batterie,lithium"
    py scripts/discover_sources.py --q "battery recycling" --portal us_ckan
    py scripts/discover_sources.py --q "elv" --list-portals

产出
----
    outputs/discovered_sources_<时间戳>.jsonl
    outputs/discovered_sources_<时间戳>.md     （人工挑选用）
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.relevance import judge       # noqa: E402
OUT = ROOT / "outputs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# ============================================================
# 平台注册表
# ------------------------------------------------------------
# ⭐ 这张表就是"关键词 → 哪里会有数据"的知识沉淀。
#    新增门户时优先做两件事：① 看它跑在哪个平台软件上 ② 用平台 API
# ============================================================
PORTALS: dict[str, dict] = {
    # ---------- 欧盟成员国层（法国）----------
    "fr_ademe": {
        "name": "法国 ADEME 开放数据",
        "platform": "datafair",
        "api": "https://data.ademe.fr/data-fair/api/v1/datasets",
        "region": "EU-MemberState/FR",
        "note": "VHU（报废车）REP 全套指标 + 生产者名录；未被地域封锁（主站 ademe.fr 被封锁）",
    },
    "fr_datagouv": {
        "name": "法国政府开放数据",
        "platform": "datagouv",
        "api": "https://www.data.gouv.fr/api/1/datasets/",
        "region": "EU-MemberState/FR",
        "note": "国家级门户，聚合各部委数据集",
    },
    # ---------- 欧盟 ----------
    "eu_data": {
        "name": "欧盟开放数据门户",
        "platform": "eu_hub",       # ⚠️ 不是标准 CKAN，结构特殊
        "api": "https://data.europa.eu/api/hub/search/search",
        "region": "EU",
        "note": "欧盟机构 + 成员国聚合；title 为 26 语言字典",
    },
    # ---------- 美国 ----------
    "us_ckan": {
        "name": "美国政府开放数据目录",
        "platform": "ckan",
        "api": "https://catalog.data.gov/api/3/action/package_search",
        "region": "US",
        "note": "联邦级数据集总目录",
    },
    "us_socrata": {
        "name": "Socrata 门户群（州/市级）",
        "platform": "socrata",
        "api": "https://api.us.socrata.com/api/catalog/v1",
        "region": "US/State-Local",
        "note": "加州等州级数据多在此；可按 q= 跨门户搜索",
    },
    "uk_ckan": {
        "name": "英国政府开放数据",
        "platform": "ckan",
        "api": "https://data.gov.uk/api/3/action/package_search",
        "region": "UK",
        "note": "英国 ELV/电池政策的配套数据",
    },
}


# ============================================================
# 后置相关性过滤 —— 所有开放数据门户的搜索都是**模糊 OR 匹配**
# ------------------------------------------------------------
# ⭐ 实测（2026-09-11）与 Federal Register API 完全同一个坑：
#      「black mass」  → 24261 个（Black Grouse 黑琴鸡、地下水体…）
#      「elv directive」→ 88478 个（Elves / Elvens…）—— 前缀匹配灾难
#      「battery recycling」→ 11 个里混着 Annual Waste Volumes / Open Air Chicago
#   门户的 q= 参数**几乎都是 OR 模糊匹配**，不后置过滤就是白跑。
#
# 两道关卡：
#   ① 所有实义词（词边界）必须都出现 —— 把 "black mass" 真正当短语
#   ② 领域相关性判定（复用 app/core/relevance）—— 把"回收站地图"这类排掉
# ============================================================
STOPWORDS = {"a", "an", "the", "of", "for", "and", "or", "to", "in", "on",
             "with", "from", "by", "at", "as", "is", "are", "be"}


def _phrase_hit(text: str, query: str) -> bool:
    """实义词全部命中（词边界 + 复数容忍）才算。

    ⚠️ 必须容忍复数：实测 `\bbattery\b` 匹配不上「UK Portable **Batteries**
    Data Summary」，把真数据集误杀了。英/法/德三种语言的复数形式各不同。
    """
    toks = [t for t in re.split(r"\W+", query.lower()) if t and t not in STOPWORDS]
    if not toks:
        return True
    low = text.lower()
    for t in toks:
        stem = t[:-1] if len(t) > 4 and t.endswith("y") else t   # battery → batter
        if not re.search(rf"\b{re.escape(stem)}\w{{0,3}}\b", low):
            return False
    return True


# ============================================================
# 跨语言概念扩展 —— 欧盟工作的刚需
# ------------------------------------------------------------
# ⭐ 同一个东西，各成员国叫法完全不同：
#     报废车：EN end-of-life vehicle ｜ FR VHU ｜ DE Altfahrzeug
#     电池：  EN battery ｜ FR batterie/pile ｜ DE Batterie
#     黑粉：  EN black mass ｜ FR masse noire ｜ DE Schwarzmasse
#   只用英语检索成员国的数据门户，会**全军覆没**（实测 ADEME：
#   "battery recycling" 过滤后 0 条，而法语 "vhu" 能拿到 9 个 REP 数据集）。
# ============================================================
CONCEPTS: dict[str, dict[str, list[str]]] = {
    "elv": {
        "en": ["end-of-life vehicle", "ELV", "vehicle recycling", "depollution"],
        "fr": ["VHU", "véhicule hors d'usage", "dépollution véhicule"],
        "de": ["Altfahrzeug", "Fahrzeugverwertung"],
    },
    "battery": {
        "en": ["battery", "lithium battery", "li-ion"],
        "fr": ["batterie", "pile", "accumulateur"],
        "de": ["Batterie", "Akku", "Akkumulator"],
    },
    "blackmass": {
        "en": ["black mass"],
        "fr": ["masse noire"],
        "de": ["Schwarzmasse"],
    },
    "recycling": {
        "en": ["recycling", "recycled content", "recycling efficiency"],
        "fr": ["recyclage", "taux de recyclage", "valorisation"],
        "de": ["Recycling", "Verwertung"],
    },
    "epr": {
        "en": ["extended producer responsibility", "producer responsibility"],
        "fr": ["REP", "responsabilité élargie du producteur"],
        "de": ["erweiterte Herstellerverantwortung"],
    },
    "shredder": {
        "en": ["shredder", "shredding"],
        "fr": ["broyeur", "broyage"],
        "de": ["Schredder"],
    },
    "waste_shipment": {
        "en": ["waste shipment", "transboundary movement"],
        "fr": ["transfert de déchets", "mouvement transfrontalier"],
        "de": ["Abfallverbringung"],
    },
}


def expand_concepts(names: list[str]) -> list[str]:
    """把概念名展开为多语言检索词。"""
    out: list[str] = []
    for n in names:
        c = CONCEPTS.get(n.strip().lower())
        if not c:
            out.append(n)                     # 不是概念名 → 当普通关键词
            continue
        for lang in ("en", "fr", "de"):
            out += c.get(lang, [])
    # 去重保序
    seen, uniq = set(), []
    for t in out:
        if t.lower() not in seen:
            seen.add(t.lower())
            uniq.append(t)
    return uniq


def _score_item(it: dict, query: str) -> tuple[bool, str, float]:
    """返回 (是否保留, 理由, 分数)。"""
    title = _as_text(it.get("title"))
    blob = f"{title} {_as_text(it.get('org'))}"
    if not title:
        return False, "empty_title", 0.0
    phrase = _phrase_hit(blob, query)
    v = judge(blob, title, scenario="policy")
    if phrase and v.relevant:
        return True, "phrase+domain", 0.9
    if phrase:
        return True, "phrase_only", 0.5      # 短语真命中，但领域词不强
    if v.relevant:
        return True, "domain_only", 0.4
    return False, "fuzzy_only", 0.0            # 门户模糊匹配的噪声


def _get(client: httpx.Client, url: str) -> dict | None:
    try:
        r = client.get(url, timeout=40)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:  # noqa: BLE001
        return None


# ============================================================
# 各平台适配器 —— 统一返回 [{title, url, org, updated, platform}]
# ============================================================
def _as_text(v, prefer: str = "en") -> str:
    """把可能是 str / None / 多语言 dict 的字段统一成字符串。

    为什么需要：不同门户的字段类型并不一致。欧盟开放数据门户的 title 是
    `{en: "...", fr: "...", ...}`（26 种语言），而 CKAN 是纯字符串。
    不统一就会拿到 dict，下游 [:74] 切片直接 TypeError。
    """
    if isinstance(v, dict):
        return str(v.get(prefer) or next(iter(v.values()), "") or "")
    return str(v or "")


def search_eu_hub(client: httpx.Client, api: str, q: str, size: int) -> list[dict]:
    """欧盟开放数据门户（data.europa.eu）—— **不是标准 CKAN**，结构特殊。

    返回：{result: {count, results: [{title: {lang: str}, id, catalog, country}]}}
    """
    d = _get(client, f"{api}?q={quote(q)}&limit={size}")
    if not d:
        return []
    res = (d.get("result") or {})
    out = []
    for r in (res.get("results") or []):
        did = r.get("id") or ""
        out.append({
            "title": _as_text(r.get("title")),
            "url": f"https://data.europa.eu/data/datasets/{did}" if did else "",
            "org": _as_text((r.get("catalog") or {}).get("title")),
            "updated": None,
            "extra": {"count": res.get("count"),
                      "country": _as_text((r.get("country") or {}).get("label"))},
        })
    return out


def search_datafair(client: httpx.Client, api: str, q: str, size: int) -> list[dict]:
    d = _get(client, f"{api}?size={size}&q={quote(q)}")
    if not d:
        return []
    return [{
        "title": _as_text(r.get("title")),
        "url": f"https://data.ademe.fr/datasets/{r.get('slug') or r.get('id')}",
        "org": (r.get("owner") or {}).get("name") if isinstance(r.get("owner"), dict) else None,
        "updated": r.get("updatedAt") or r.get("createdAt"),
        "extra": {"count": d.get("count")},
    } for r in (d.get("results") or [])]


def search_ckan(client: httpx.Client, api: str, q: str, size: int) -> list[dict]:
    d = _get(client, f"{api}?q={quote(q)}&rows={size}")
    if not d:
        return []
    res = (d.get("result") or {}).get("results") or []
    return [{
        "title": _as_text(r.get("title") or r.get("name")),
        "url": r.get("url") or (f"https://catalog.data.gov/dataset/{r.get('name')}"
                                if "data.gov" in api else _as_text(r.get("name"))),
        "org": _as_text((r.get("organization") or {}).get("title")) if isinstance(
            r.get("organization"), dict) else None,
        "updated": r.get("metadata_modified"),
        "extra": {"count": (d.get("result") or {}).get("count")},
    } for r in res]


def search_datagouv(client: httpx.Client, api: str, q: str, size: int) -> list[dict]:
    d = _get(client, f"{api}?q={quote(q)}&page_size={size}")
    if not d:
        return []
    return [{
        "title": _as_text(r.get("title")),
        "url": r.get("page") or "",
        "org": (r.get("organization") or {}).get("name") if isinstance(
            r.get("organization"), dict) else None,
        "updated": r.get("last_update"),
        "extra": {"count": d.get("total")},
    } for r in (d.get("data") or [])]


def search_socrata(client: httpx.Client, api: str, q: str, size: int) -> list[dict]:
    d = _get(client, f"{api}?q={quote(q)}&limit={size}&only=dataset")
    if not d:
        return []
    return [{
        "title": _as_text((r.get("resource") or {}).get("name")),
        "url": _as_text(r.get("permalink") or (r.get("resource") or {}).get("id")),
        "org": next((m.get("value") for m in ((r.get("classification") or {})
                                               .get("domain_metadata") or [])
                     if m.get("key") == "Agency"), None),
        "updated": (r.get("resource") or {}).get("updatedAt"),
        "extra": {"count": d.get("resultSetSize")},
    } for r in (d.get("results") or [])]


ADAPTERS = {
    "datafair": search_datafair,
    "ckan": search_ckan,
    "datagouv": search_datagouv,
    "socrata": search_socrata,
    "eu_hub": search_eu_hub,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="数据源发现器（关键词 → 哪里会有数据）")
    ap.add_argument("--q", default="battery recycling",
                    help="关键词，逗号分隔可多个")
    ap.add_argument("--concept", default="",
                    help="概念名（自动展开为 EN/FR/DE 多语言词）："
                         "elv, battery, blackmass, recycling, epr, shredder, waste_shipment")
    ap.add_argument("--portal", default="all", help="门户 id，或 all")
    ap.add_argument("--size", type=int, default=10, help="每个关键词每门户取回条数")
    ap.add_argument("--raw", action="store_true",
                    help="不过滤，输出门户原始结果（看模糊匹配有多离谱时用）")
    ap.add_argument("--list-portals", action="store_true")
    args = ap.parse_args()

    if args.list_portals:
        print(f"{'id':<16}{'platform':<11}{'region':<20}name")
        print("-" * 96)
        for pid, p in PORTALS.items():
            print(f"{pid:<16}{p['platform']:<11}{p['region']:<20}{p['name']}")
        print("\n可用概念：" + ", ".join(CONCEPTS))
        return 0

    OUT.mkdir(exist_ok=True)
    keywords = [k.strip() for k in args.q.split(",") if k.strip()]
    if args.concept:
        concepts = [c.strip() for c in args.concept.split(",") if c.strip()]
        expanded = expand_concepts(concepts)
        unknown = [c for c in concepts if c.lower() not in CONCEPTS]
        print(f"概念扩展：{', '.join(concepts)} → {len(expanded)} 个多语言词"
              + (f"（未知概念按原词处理：{unknown}）" if unknown else ""))
        keywords = expanded + keywords
        # 去重保序
        seen, kk = set(), []
        for k in keywords:
            if k.lower() not in seen:
                seen.add(k.lower())
                kk.append(k)
        keywords = kk
    targets = (list(PORTALS) if args.portal == "all"
               else [x.strip() for x in args.portal.split(",") if x.strip()])

    rows: list[dict] = []
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        for pid in targets:
            p = PORTALS.get(pid)
            if not p:
                print(f"未知门户：{pid}")
                continue
            adapter = ADAPTERS[p["platform"]]
            print(f"\n{'=' * 92}\n {p['name']}  [{p['platform']}]  {p['region']}\n{'=' * 92}")
            for kw in keywords:
                try:
                    items = adapter(client, p["api"], kw, args.size)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ⚠️ 「{kw}」失败：{type(exc).__name__}")
                    continue
                total = (items[0]["extra"].get("count") if items else 0)
                kept, dropped = [], 0
                for it in items:
                    if args.raw:
                        kept.append({**it, "_why": "raw", "_score": 0.0})
                        continue
                    ok, why, score = _score_item(it, kw)
                    if ok:
                        kept.append({**it, "_why": why, "_score": score})
                    else:
                        dropped += 1
                print(f"  「{kw}」→ 门户报 {total} 个"
                      f"｜取回 {len(items)}｜过滤后保留 {len(kept)}（模糊噪声 {dropped}）")
                for it in kept:
                    title = _as_text(it.get("title"))
                    flag = {"phrase+domain": "✅", "phrase_only": "🟡",
                            "domain_only": "🔵", "raw": "  "}.get(it["_why"], "  ")
                    print(f"      {flag} {title[:70]:<72} [{kw}]")
                    rows.append({**it, "title": title, "keyword": kw, "portal_id": pid,
                                 "portal_name": p["name"], "platform": p["platform"],
                                 "region": p["region"], "fuzzy_dropped": dropped})
                time.sleep(1.0)              # 采集礼仪

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    jl = OUT / f"discovered_sources_{stamp}.jsonl"
    with jl.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    md = OUT / f"discovered_sources_{stamp}.md"
    lines = [f"# 数据源发现结果 · {stamp}", "",
             f"关键词：{', '.join(keywords)}　门户：{len(targets)} 个　候选数据集：{len(rows)}", ""]
    by_portal: dict[str, list[dict]] = {}
    for r in rows:
        by_portal.setdefault(r["portal_name"], []).append(r)
    for name, items in by_portal.items():
        lines += [f"## {name}（{len(items)}）", ""]
        for it in items:
            lines.append(f"- **{it['title']}**　`{it['keyword']}`")
            if it.get("url"):
                lines.append(f"  - {it['url']}")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'=' * 92}")
    print(f" 合计候选 {len(rows)} 条")
    print(f" → {jl.relative_to(ROOT)}")
    print(f" → {md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
