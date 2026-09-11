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
        "note": "⚠️ 与 fr_gouv 同一端点（重复登记）—— 以 fr_gouv 为准，保留本条目只为兼容旧调用",
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
        # ⚠️ 实测（2026-09-11）：该端点已失效（/api/3/ 与 /api/ 均 404），
        #    catalog.data.gov 已迁移。美国侧改用：
        #      us_federal（Federal Register 政策）
        #      us_socrata（州/市级开放数据，实测可用）
        "deprecated": True,
        "note": "🚫 端点已失效，保留条目以记录探测结论",
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
    # ============================================================
    # 欧盟成员国层（逐个实测端点后才登记 —— 猜端点会白跑）
    # ------------------------------------------------------------
    # ⚠️ 实测教训（2026-09-11）：
    #   ① 端点路径必须实测。`govdata.de/api/…` → 不可达；
    #      `govdata.de/ckan/api/…` → 200 ✅（多一层 /ckan/）
    #   ② **curl 失败 ≠ 不可达**：波兰 `api.dane.gov.pl` curl 返回 000，
    #      浏览器却是 200。与之前"Python TLS 栈连不上但 curl 正常"正好相反。
    #      → 判定端点失效前要 **curl 与浏览器双向交叉验证**。
    # ============================================================
    "de_govdata": {
        "name": "德国 GovData（联邦开放数据门户）",
        "platform": "ckan",
        "api": "https://www.govdata.de/ckan/api/3/action/package_search",
        "region": "EU-MemberState/DE",
        "note": "147,453 个数据集；⚠️ 路径多一层 /ckan/",
    },
    "nl_data": {
        "name": "荷兰 data.overheid.nl",
        "platform": "ckan",
        "api": "https://data.overheid.nl/data/api/3/action/package_search",
        "region": "EU-MemberState/NL",
        "note": "荷兰国家级开放数据",
    },
    "be_data": {
        "name": "比利时 data.gov.be",
        "platform": "ckan",
        # ⚠️ 必须带语言前缀 /en/ —— 缺了会直接回 HTML 反爬页（不是 404，更隐蔽）
        #    实测：/api/3/action/... → 200 但 content-type=text/html（机器人防护页）
        #          /en/api/3/action/... → 200 且是真 JSON ✅
        "api": "https://data.gov.be/en/api/3/action/package_search",
        "region": "EU-MemberState/BE",
        "note": "联邦级；法语/荷语双语术语都要试",
    },
    "ie_data": {
        "name": "爱尔兰 data.gov.ie",
        "platform": "ckan",
        "api": "https://data.gov.ie/api/3/action/package_search",
        "region": "EU-MemberState/IE",
        "note": "英语，检索门槛最低",
    },
    "pt_dados": {
        "name": "葡萄牙 dados.gov.pt",
        "platform": "datagouv",
        "api": "https://dados.gov.pt/api/1/datasets/",
        "region": "EU-MemberState/PT",
        "note": "与法国 data.gouv.fr 同构",
    },
    "pl_dane": {
        "name": "波兰 dane.gov.pl",
        "platform": "dane_gov_pl",
        "api": "https://api.dane.gov.pl/1.4/datasets",
        "region": "EU-MemberState/PL",
        "note": "⚠️ curl 返回 000，浏览器 200 —— 端点本身可用，是网络栈问题",
    },
    "fr_gouv": {
        "name": "法国政府开放数据",
        "platform": "datagouv",
        "api": "https://www.data.gouv.fr/api/1/datasets/",
        "region": "EU-MemberState/FR",
        "note": "国家级门户，聚合各部委数据集（与 fr_datagouv 同一站，保留此条为准）",
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
#             NL autowrak ｜ PL pojazd wycofany ｜ PT veículo em fim de vida
#     电池：  EN battery ｜ FR batterie/pile ｜ DE Batterie/Akku
#             NL batterij/accu ｜ PL bateria/akumulator ｜ PT bateria/pilha
#   只用英语检索成员国的数据门户，会**全军覆没**（实测 ADEME：
#   "battery recycling" 过滤后 0 条，而法语 "vhu" 能拿到 9 个 REP 数据集）。
#
# ⚠️ 新增语言时**必须同步** `app/core/relevance_browser.py` 的
#    BROWSER_FOCUS_ANCHORS，否则会出现"检索到了却判为不相关"。
# ============================================================
CONCEPTS: dict[str, dict[str, list[str]]] = {
    "elv": {
        "en": ["end-of-life vehicle", "ELV", "vehicle recycling", "depollution"],
        "fr": ["VHU", "véhicule hors d'usage", "dépollution véhicule"],
        "de": ["Altfahrzeug", "Fahrzeugverwertung"],
        "nl": ["autowrak", "afgedankte voertuigen", "autodemontage"],
        "pl": ["pojazd wycofany z eksploatacji", "samochód wycofany", "autozłom"],
        "pt": ["veículo em fim de vida", "VFV", "desmantelamento"],
        "es": ["vehículo fuera de uso", "VFU", "desguace"],
        "it": ["veicolo fuori uso", "VFU", "autodemolizione"],
    },
    "battery": {
        "en": ["battery", "lithium battery", "li-ion"],
        "fr": ["batterie", "pile", "accumulateur"],
        "de": ["Batterie", "Akku", "Akkumulator"],
        "nl": ["batterij", "accu"],
        "pl": ["bateria", "akumulator"],
        "pt": ["bateria", "pilha", "acumulador"],
        "es": ["batería", "pila", "acumulador"],
        "it": ["batteria", "pila", "accumulatore"],
    },
    "blackmass": {
        "en": ["black mass"],
        "fr": ["masse noire"],
        "de": ["Schwarzmasse"],
        "nl": ["zwarte massa"],
        "pl": ["masa czarna"],
        "pt": ["massa negra"],
        "es": ["masa negra"],
        "it": ["massa nera"],
    },
    "recycling": {
        "en": ["recycling", "recycled content", "recycling efficiency"],
        "fr": ["recyclage", "taux de recyclage", "valorisation"],
        "de": ["Recycling", "Verwertung"],
        "nl": ["recycling", "recyclage", "verwerking"],
        "pl": ["recykling", "odzysk"],
        "pt": ["reciclagem", "valorização"],
        "es": ["reciclaje", "valorización"],
        "it": ["riciclaggio", "recupero"],
    },
    "epr": {
        "en": ["extended producer responsibility", "producer responsibility"],
        "fr": ["REP", "responsabilité élargie du producteur"],
        "de": ["erweiterte Herstellerverantwortung"],
        "nl": ["uitgebreide producentenverantwoordelijkheid"],
        "pl": ["rozszerzona odpowiedzialność producenta"],
        "pt": ["responsabilidade alargada do produtor"],
        "es": ["responsabilidad ampliada del productor"],
        "it": ["responsabilità estesa del produttore"],
    },
    "shredder": {
        "en": ["shredder", "shredding"],
        "fr": ["broyeur", "broyage"],
        "de": ["Schredder"],
        "nl": ["versnipperaar", "shredder"],
        "pl": ["strzępiarka", "rozdrabnianie"],
        "pt": ["triturador", "trituração"],
        "es": ["triturador", "fragmentación"],
        "it": ["trituratore", "triturazione"],
    },
    "waste_shipment": {
        "en": ["waste shipment", "transboundary movement"],
        "fr": ["transfert de déchets", "mouvement transfrontalier"],
        "de": ["Abfallverbringung"],
        "nl": ["afvaltransport", "grensoverschrijdende overbrenging"],
        "pl": ["przemieszczanie odpadów"],
        "pt": ["transferência de resíduos"],
        "es": ["traslado de residuos"],
        "it": ["spedizione di rifiuti"],
    },
}

ALL_LANGS: tuple[str, ...] = ("en", "fr", "de", "nl", "pl", "pt", "es", "it")


def expand_concepts(names: list[str],
                    langs: tuple[str, ...] | None = None) -> list[str]:
    """把概念名展开为多语言检索词。

    langs 给定时只展开这些语言（例如只做德语区就传 ("de",)）；
    不给则展开 ALL_LANGS 里该概念有的全部语言。
    """
    out: list[str] = []
    for n in names:
        c = CONCEPTS.get(n.strip().lower())
        if not c:
            out.append(n)                     # 不是概念名 → 当普通关键词
            continue
        for lang, terms in c.items():
            if langs and lang not in langs:
                continue
            out += terms
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


def search_dane_gov_pl(client: httpx.Client, api: str, q: str, size: int) -> list[dict]:
    """波兰 dane.gov.pl（JSON:API 风格，结构与 CKAN 不同）。

    ⚠️ 该端点 curl 返回 000 但浏览器 200 —— 若 httpx 也连不上，
    会把异常抛给调用方，由 --probe-portals 报告出来。
    """
    d = _get(client, f"{api}?q={quote(q)}&per_page={size}")
    if not d:
        return []
    rows = d.get("data") or []
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        attr = r.get("attributes") or r
        out.append({
            "title": _as_text(attr.get("title")),
            "url": f"https://dane.gov.pl/dataset/{r.get('id')}" if r.get("id") else "",
            "org": _as_text((attr.get("institution") or {}).get("name")
                            if isinstance(attr.get("institution"), dict) else None),
            "updated": attr.get("modified") or attr.get("created"),
            "extra": {"count": (d.get("meta") or {}).get("count")},
        })
    return out


ADAPTERS = {
    "datafair": search_datafair,
    "ckan": search_ckan,
    "datagouv": search_datagouv,
    "socrata": search_socrata,
    "eu_hub": search_eu_hub,
    "dane_gov_pl": search_dane_gov_pl,
}


# ============================================================
# 端点体检 —— 这就是「根据结果修正方案」的可复现形式
# ------------------------------------------------------------
# 每新增一个门户都应先跑一次：能连上吗？返回结构对得上吗？命中几条？
# 不要在"猜的端点"上写业务逻辑。
# ============================================================
def probe_portals(targets: list[str]) -> int:
    """端点体检。

    ⚠️ 探针词必须**多语言**（2026-09-11 踩过的坑）：
       首版只用英语 "battery" 探所有门户 → 法/荷/葡门户全部返回 0，
       被误报为"返回为空"。但那不是故障，是**探针语言不对**。
       一个错探针会把好门户判死，比不体检更糟。
    """
    probes = [("en", "battery"), ("fr", "batterie"), ("de", "Batterie"),
              ("nl", "batterij"), ("pl", "bateria"), ("pt", "bateria")]
    print(f"{'portal':<14}{'platform':<12}{'HTTP':>6}{'最佳命中':>9}  探针 / 状态")
    print("-" * 96)
    bad = 0
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True) as client:
        for pid in targets:
            p = PORTALS.get(pid)
            if not p:
                print(f"{pid:<14}{'?':<12}{'—':>6}{'—':>9}  ❓ 未登记")
                bad += 1
                continue
            adapter = ADAPTERS.get(p["platform"])
            if adapter is None:
                print(f"{pid:<14}{p['platform']:<12}{'—':>6}{'—':>9}  ❓ 无适配器")
                bad += 1
                continue

            best_n, best_lang, err = 0, "", None
            shape_ok = False
            any_items = False
            for lang, term in probes:
                try:
                    items = adapter(client, p["api"], term, 3)
                except Exception as exc:  # noqa: BLE001
                    err = type(exc).__name__
                    continue
                if items:
                    any_items = True
                n = (items[0]["extra"].get("count") if items else 0) or len(items)
                if items and all(_as_text(i.get("title")) for i in items):
                    shape_ok = True
                if n > best_n:
                    best_n, best_lang = n, lang

            tag = "🚫 已弃用" if p.get("deprecated") else ""
            if tag:
                print(f"{pid:<14}{p['platform']:<12}{'—':>6}{'—':>9}  {tag}（{p.get('note','')}）")
                continue
            if err and not any_items:
                print(f"{pid:<14}{p['platform']:<12}{'ERR':>6}{'—':>9}  "
                      f"❌ {err}（试浏览器通道交叉验证）")
                bad += 1
            elif shape_ok and best_n > 0:
                print(f"{pid:<14}{p['platform']:<12}{'200':>6}{best_n:>9}  "
                      f"✅ 最佳探针 {best_lang}（{len(probes)} 语言已试）")
            elif best_n == 0 and any_items:
                # 有结果但标题都空 → 结构真的对不上
                print(f"{pid:<14}{p['platform']:<12}{'200':>6}{best_n:>9}  ⚠️ 标题解析异常")
                bad += 1
            elif best_n == 0:
                # ⚠️ 与上面区分开：这才是真正的"零命中"（可能领域无关）
                print(f"{pid:<14}{p['platform']:<12}{'200':>6}{best_n:>9}  "
                      f"⚠️ 结构正常但 {len(probes)} 语言全零命中")
            else:
                print(f"{pid:<14}{p['platform']:<12}{'200':>6}{best_n:>9}  ⚠️ 返回非 JSON（疑拦截页）")
                bad += 1
    print("-" * 96)
    print(f"  {len(targets) - bad}/{len(targets)} 个门户端点可用")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="数据源发现器（关键词 → 哪里会有数据）")
    ap.add_argument("--q", default="battery recycling",
                    help="关键词，逗号分隔可多个")
    ap.add_argument("--concept", default="",
                    help="概念名（自动展开为多语言词）："
                         "elv, battery, blackmass, recycling, epr, shredder, waste_shipment")
    ap.add_argument("--langs", default="",
                    help=f"限定概念展开的语言，逗号分隔（可用：{','.join(ALL_LANGS)}）；"
                         "不传则展开全部")
    ap.add_argument("--portal", default="all", help="门户 id，或逗号分隔多个 / all")
    ap.add_argument("--size", type=int, default=10, help="每个关键词每门户取回条数")
    ap.add_argument("--raw", action="store_true",
                    help="不过滤，输出门户原始结果（看模糊匹配有多离谱时用）")
    ap.add_argument("--list-portals", action="store_true", help="列出所有门户与概念")
    ap.add_argument("--probe-portals", action="store_true",
                    help="⭐ 端点体检：逐个验证 API 能不能连、结构对不对")
    args = ap.parse_args()

    if args.list_portals:
        print(f"{'id':<16}{'platform':<12}{'region':<22}name")
        print("-" * 100)
        for pid, p in PORTALS.items():
            print(f"{pid:<16}{p['platform']:<12}{p['region']:<22}{p['name']}")
        print("\n可用概念：" + ", ".join(CONCEPTS))
        print("可用语言：" + ", ".join(ALL_LANGS))
        return 0

    if args.probe_portals:
        targets = (list(PORTALS) if args.portal == "all"
                   else [x.strip() for x in args.portal.split(",") if x.strip()])
        return probe_portals(targets)

    OUT.mkdir(exist_ok=True)
    keywords = [k.strip() for k in args.q.split(",") if k.strip()]
    if args.concept:
        concepts = [c.strip() for c in args.concept.split(",") if c.strip()]
        langs = (tuple(x.strip() for x in args.langs.split(",") if x.strip())
                 if args.langs else None)
        expanded = expand_concepts(concepts, langs)
        unknown = [c for c in concepts if c.lower() not in CONCEPTS]
        print(f"概念扩展：{', '.join(concepts)}"
              + (f"（限 {'/'.join(langs)}）" if langs else "（全语言）")
              + f" → {len(expanded)} 个多语言词"
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
