# -*- coding: utf-8 -*-
"""run_jurisdiction_round.py —— 管辖地级 MODE A/B 轮执行器（Phase 4B-2A Step 8）。

与 run_discovery_round.py 同样的协议（plan 绑定 / validity / 双指标），
但作用于**管辖地级 plan**（scope == jurisdiction_id，如 SE）。

路线语义（自管辖地端点派生的 4 类独立路线）：
    A 官方枚举     ：plan.fr_agencies（文号/section 直链种子）→ 抓全文
    B 母语全文检索 ：plan.fr_terms → 官方检索页 → 解析新文号 → 抓全文
    C 引用扩展     ：plan.eu_keywords（显式引用种子）+ 已采语料正文引用抽取 → 回采
    D 缺口枚举     ：plan.cross_terms（显式缺口种子）→ 回采

支持管辖地：SE / FI / US-CA / US-WA（其余如实拒绝——通道未适配）。
每个管辖地的 search/fetch 实现复用 leg_utils 解析基元；证据字段口径与
正式连接器一致（evidence_id / doc_key / jurisdiction / source_role）。

用法：
    py scripts/run_jurisdiction_round.py --plan SE_PLAN_V1 --mode discovery --round 1
    py scripts/run_jurisdiction_round.py --show

产物：
    outputs/discovery_rounds/round_{scope}_{n}_{ts}.json
    outputs/round_{scope}_{n}_{ts}.jsonl（新入选文档）
    outputs/audit/discovery_rounds.json（索引，与联邦轮共用）
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import html as html_mod
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.connectors.leg_utils import (  # noqa: E402
    detect_challenge, extract_next_flight, extract_text_nodes, strip_html,
    trim_nav,
)
from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.backfill import load_records  # noqa: E402
from app.policy.rounds import (  # noqa: E402
    ACCEPTED_CLASSES, RouteResult, build_round_record, convergence_status,
    derive_validity, now_iso,
)
from app.policy.search_plan import load_plan, validate_plan  # noqa: E402

ROUNDS_DIR = ROOT / "outputs" / "discovery_rounds"
INDEX = ROOT / "outputs" / "audit" / "discovery_rounds.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
SUPPORTED = ("SE", "FI", "US-CA", "US-WA")


class DocNotFound(Exception):
    """文号/section 不存在（框架页）——负结果，不计 source_failure。"""


# ------------------------------------------------------------ 工具

async def _get(client: httpx.AsyncClient, url: str, *, params=None,
               headers=None):
    """GET + 瞬态重试 1 次。返回 (response, recovered)。"""
    try:
        return await client.get(url, params=params, headers=headers), False
    except Exception:  # noqa: BLE001
        await asyncio.sleep(2)
        return await client.get(url, params=params, headers=headers), True


def _mk_record(*, evidence_id: str, source_id: str, jurisdiction: str,
               region: str, url: str, title: str, doc_key: str, text: str,
               collector: str, source_role: str, language: str,
               nav_trimmed: int, route: str) -> dict:
    return {
        "evidence_id": evidence_id, "channel": "connector",
        "source_id": source_id, "region": region, "url": url,
        "title": title, "publish_date": "",
        "meta": {"region": region, "jurisdiction": jurisdiction,
                 "doc_key": doc_key, "page_title": "",
                 "nav_trimmed_chars": nav_trimmed, "collector": collector,
                 "language": language, "source_role": source_role,
                 "discovered_by_round_route": route},
        "text": text,
    }


# ------------------------------------------------------------ SE

async def se_search(client, term: str) -> list[dict]:
    """fritext 检索 → [{title, doc}]（search-hit 块：标题 + SFS-nummer）。"""
    r, _ = await _get(client, "https://rkrattsbaser.gov.se/sfst",
                      params={"fritext": term}, headers=UA)
    hits = []
    for m in re.finditer(
            r'<div class="search-hit">.*?<a href="[^"]*">(.*?)</a>.*?'
            r"SFS-nummer:\s*(\d{4}:\d+)", r.text, re.S):
        hits.append({"title": html_mod.unescape(
            re.sub(r"<[^>]+>", "", m.group(1))).strip(),
            "doc": m.group(2)})
    return hits


async def se_fetch(client, doc: str) -> dict | None:
    url = f"https://rkrattsbaser.gov.se/sfst?bet={doc}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 1500:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    year, num = doc.split(":")
    return _mk_record(
        evidence_id=f"se_sfst_{doc.replace(':', '_')}", source_id="se_sfst",
        jurisdiction="SE", region="EU", url=url,
        title=f"SFS {doc}", doc_key=f"SE:SFS:{doc}", text=body[:60000],
        collector="jurisdiction_round", source_role="MS_LEGISLATION_DATABASE",
        language="sv", nav_trimmed=nav, route="")


# ------------------------------------------------------------ FI

async def fi_search(client, term: str) -> list[dict]:
    """haku 检索 → 链接 /fi/lainsaadanto/YYYY/NNN → {doc=YYYYNNNN}。"""
    r, _ = await _get(client, "https://www.finlex.fi/fi/haku",
                      params={"q": term}, headers=UA)
    text = r.text + ("\n" + (extract_next_flight(r.text) or ""))
    out, seen = [], set()
    for year, num in re.findall(
            r"/fi/lainsaadanto/(\d{4})/(\d+)(?![\d\-])", text):
        if (year, num) in seen:
            continue
        seen.add((year, num))
        out.append({"doc": f"{year}{int(num):04d}", "year": year, "num": num})
    return out


async def fi_fetch(client, doc: str) -> dict | None:
    year = doc[:4]
    url = f"https://www.finlex.fi/fi/laki/ajantasa/{year}/{doc}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    flight = extract_next_flight(r.text)
    nodes = extract_text_nodes(flight) if flight else ""
    if len(nodes) >= 2000:
        text = nodes
    elif flight:
        text = strip_html(flight)
    else:
        text = strip_html(r.text)
    if len(text) < 2000:
        raise DocNotFound(f"skeleton_or_empty({len(text)} chars)")
    body, nav = trim_nav(text)
    num = str(int(doc[4:]))
    return _mk_record(
        evidence_id=f"fi_finlex_{doc}", source_id="fi_finlex",
        jurisdiction="FI", region="EU", url=url,
        title=f"SDK {num}/{year}", doc_key=f"FI:SDK:{year}/{num}",
        text=body[:60000], collector="jurisdiction_round",
        source_role="MS_LEGISLATION_DATABASE", language="fi",
        nav_trimmed=nav, route="")


# ------------------------------------------------------------ US-CA

async def ca_fetch(client, doc: str) -> dict | None:
    """doc = 'PRC:42451' 或 'PRC:42451.5'。"""
    law_code, section = doc.split(":", 1)
    url = ("https://leginfo.legislature.ca.gov/faces/"
           f"codes_displaySection.xhtml?lawCode={law_code}"
           f"&sectionNum={section}")
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 800:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    return _mk_record(
        evidence_id=f"us_ca_leginfo_{section.replace('.', '_')}",
        source_id="us_ca_leginfo", jurisdiction="US-CA", region="US",
        url=url, title=f"CA {law_code} Code Section {section}",
        doc_key=f"US-CA:{law_code}:{section}", text=body[:60000],
        collector="jurisdiction_round", source_role="STATE_STATUTES",
        language="en", nav_trimmed=nav, route="")


# ------------------------------------------------------------ US-WA

async def wa_fetch(client, cite: str) -> dict | None:
    url = f"https://app.leg.wa.gov/RCW/default.aspx?cite={cite}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 800:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    return _mk_record(
        evidence_id=f"us_wa_rcw_{cite.replace('.', '_').lower()}",
        source_id="us_wa_rcw", jurisdiction="US-WA", region="US",
        url=url, title=f"RCW {cite}", doc_key=f"US-WA:RCW:{cite}",
        text=body[:60000], collector="jurisdiction_round",
        source_role="STATE_STATUTES", language="en",
        nav_trimmed=nav, route="")


# ------------------------------------------------------------ 引用抽取（C）

CITE_PATTERNS = {
    "SE": re.compile(r"SFS\s*(\d{4}:\d+)"),
    "FI": re.compile(r"(\d{1,4})/(\d{4})"),
    "US-CA": re.compile(r"Section\s+(\d{4,5}(?:\.\d+)?)\s+of\s+the\s+Public\s+Resources\s+Code", re.I),
    "US-WA": re.compile(r"RCW\s+(\d+A\.\d+\.\d+)"),
}


def _cite_to_doc(jid: str, m: re.Match) -> str:
    if jid == "SE":
        return m.group(1)
    if jid == "FI":
        num, year = int(m.group(1)), m.group(2)
        return f"{year}{num:04d}"
    if jid == "US-CA":
        return f"PRC:{m.group(1)}"
    return m.group(1)


def _extract_cited(jid: str, records: list[dict], existing: set[str]) -> list[str]:
    """从**自有记录**（meta.jurisdiction == jid）正文抽引用；
    跳过 NIM 元数据摘要（噪声源：文献摘要含大量年代号）。"""
    pat = CITE_PATTERNS[jid]
    docs, seen = [], set()
    for r in records:
        if (r.get("meta") or {}).get("jurisdiction") != jid:
            continue
        text = (r.get("title") or "") + "\n" + (r.get("text") or "")[:20000]
        for m in pat.finditer(text):
            doc = _cite_to_doc(jid, m)
            if doc in seen:
                continue
            seen.add(doc)
            docs.append(doc)
    return docs


# ------------------------------------------------------------ 轮执行

FETCHERS = {"SE": se_fetch, "FI": fi_fetch, "US-CA": ca_fetch, "US-WA": wa_fetch}
SEARCHERS = {"SE": se_search, "FI": fi_search}


async def _run_route_a(client, jid, plan, existing) -> RouteResult:
    rr = RouteResult("A", "official_enumeration")
    nf: list[dict] = []
    seeds = list(plan.query_set.fr_agencies)
    for seed in seeds:
        rr.queries.append(seed)
        eid_guess = None   # 由 fetcher 决定
        try:
            rec = await FETCHERS[jid](client, seed)
        except DocNotFound as exc:
            nf.append({"query": seed, "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_leg",
                                       "query": seed,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_leg"] = \
            rr.source_success.get(f"{jid.lower()}_leg", 0) + 1
        rr.raw_found += 1
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "A"
        eid_guess = rec["evidence_id"]
        if eid_guess not in existing:
            rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def _run_route_b(client, jid, plan, existing, max_fetch) -> RouteResult:
    rr = RouteResult("B", "native_fulltext_search")
    nf: list[dict] = []
    searcher = SEARCHERS.get(jid)
    if searcher is None:
        rr.source_failures.append({
            "source": f"{jid.lower()}_search",
            "failure": "no_search_endpoint（如实记录，通道缺失）"})
        return rr
    wanted: dict[str, dict] = {}
    for term in plan.query_set.fr_terms:
        rr.queries.append(term)
        try:
            hits = await searcher(client, term)
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_search",
                                       "query": term,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_search"] = \
            rr.source_success.get(f"{jid.lower()}_search", 0) + 1
        rr.raw_found += len(hits)
        for h in hits:
            doc = h["doc"]
            eid = (f"se_sfst_{doc.replace(':', '_')}" if jid == "SE"
                   else f"fi_finlex_{doc}")
            if eid in existing or eid in wanted:
                continue
            wanted[eid] = h
    fetched = 0
    for eid, h in list(wanted.items())[:max_fetch]:
        fetched += 1
        try:
            rec = await FETCHERS[jid](client, h["doc"])
        except DocNotFound as exc:
            nf.append({"query": h["doc"], "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_doc",
                                       "query": h["doc"],
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "B"
        rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def _run_route_c(client, jid, plan, existing, records,
                       max_fetch) -> RouteResult:
    rr = RouteResult("C", "legal_relation_expansion")
    nf: list[dict] = []
    seeds: list[str] = []
    # 显式引用种子（plan.eu_keywords 解析为文号）
    for kw in plan.query_set.eu_keywords:
        m = CITE_PATTERNS[jid].search(kw.replace("SDK ", "").replace("SFS ", ""))
        if m:
            seeds.append(_cite_to_doc(jid, m))
        else:
            # 形如 "RCW 70A.555.010" / "PRC Section 42451" 的通用模式
            m2 = re.search(r"(?:\d{1,4}/\d{4})|(?:\d{4}:\d+)|"
                           r"(?:\d+A\.\d+\.\d+)|(?:\d{4,5}(?:\.\d+)?)", kw)
            if m2:
                tok = m2.group(0)
                if jid == "US-CA":
                    seeds.append(f"PRC:{tok}")
                else:
                    seeds.append(tok)
    # 运行时引用抽取（语料正文）
    seeds += _extract_cited(jid, records, existing)
    seen = set()
    fetched = 0
    for doc in seeds:
        if doc in seen:
            continue
        seen.add(doc)
        eid = (f"se_sfst_{doc.replace(':', '_')}" if jid == "SE"
               else f"fi_finlex_{doc}" if jid == "FI"
               else f"us_ca_leginfo_{doc.split(':')[-1].replace('.', '_')}"
               if jid == "US-CA"
               else f"us_wa_rcw_{doc.replace('.', '_').lower()}")
        if eid in existing:
            continue
        if fetched >= max_fetch:
            break
        fetched += 1
        rr.queries.append(doc)
        try:
            rec = await FETCHERS[jid](client, doc)
        except DocNotFound as exc:
            nf.append({"query": doc, "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_cite",
                                       "query": doc,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_cite"] = \
            rr.source_success.get(f"{jid.lower()}_cite", 0) + 1
        rr.raw_found += 1
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "C"
        rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def _run_route_d(client, jid, plan, existing, max_fetch) -> RouteResult:
    rr = RouteResult("D", "gap_discovery")
    nf: list[dict] = []
    seeds = list(plan.query_set.cross_terms)
    if not seeds:
        rr.not_found = nf  # type: ignore[attr-defined]
        return rr
    fetched = 0
    for seed in seeds[:max_fetch]:
        fetched += 1
        rr.queries.append(seed)
        try:
            rec = await FETCHERS[jid](client, seed)
        except DocNotFound as exc:
            nf.append({"query": seed, "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_gap",
                                       "query": seed,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_gap"] = \
            rr.source_success.get(f"{jid.lower()}_gap", 0) + 1
        rr.raw_found += 1
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "D"
        rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def run_round(jid: str, round_no: int, plan, mode: str,
                    *, persist: bool = True, max_fetch: int = 40) -> dict:
    records = load_records(ROOT)
    existing = {str(r.get("evidence_id")) for r in records}
    started = now_iso()
    routes = list(plan.discovery_routes)
    results: list[RouteResult] = []
    async with httpx.AsyncClient(headers=UA, timeout=45,
                                 follow_redirects=True) as client:
        for r in routes:
            if r == "A":
                results.append(await _run_route_a(client, jid, plan, existing))
            elif r == "B":
                results.append(await _run_route_b(client, jid, plan, existing,
                                                  max_fetch))
            elif r == "C":
                results.append(await _run_route_c(client, jid, plan, existing,
                                                  records, max_fetch))
            elif r == "D":
                results.append(await _run_route_d(client, jid, plan, existing,
                                                  max_fetch))

    classified: dict[str, str] = {}
    topics_by_id: dict[str, list[str]] = {}
    all_candidates: dict[str, dict] = {}
    for rr in results:
        for c in rr.candidates:
            all_candidates.setdefault(c["evidence_id"], c)
    for eid, rec in all_candidates.items():
        try:
            res = classify_record(rec)
            classified[eid] = res.classification
            if res.topic_ids:
                topics_by_id[eid] = list(res.topic_ids)
        except Exception:  # noqa: BLE001
            classified[eid] = "D"
    route_dicts = [rr.as_dict(classified=classified, existing_ids=existing,
                              topics_by_id=topics_by_id) for rr in results]
    for d, rr in zip(route_dicts, results):
        d["not_found"] = getattr(rr, "not_found", [])

    failures = [f for r in route_dicts for f in (r.get("source_failures") or [])]
    success: dict[str, int] = {}
    for r in route_dicts:
        for src, n in (r.get("source_success") or {}).items():
            success[src] = success.get(src, 0) + int(n)
    critical = set(plan.critical_sources)
    crit_fail_no_success = any(
        (f.get("source") in critical) and success.get(f.get("source"), 0) == 0
        for f in failures)
    validity = derive_validity(failures=len(failures),
                               critical_failed_no_success=crit_fail_no_success)
    round_id = f"{jid}-R{round_no}-{now_iso()[:10]}"
    record = build_round_record(
        round_id=round_id, scope=jid, started_at=started, ended_at=now_iso(),
        routes=route_dicts,
        source_roles=[pr.role for pr in plan.source_roles],
        plan_id=plan.plan_id, plan_hash=plan.plan_hash(),
        round_mode=("discovery_expansion" if mode == "discovery"
                    else "convergence_validation"),
        validity=validity,
        transient_failures=sum(int(r.get("transient_recovered", 0) or 0)
                               for r in route_dicts), notes="")
    ROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_iso().replace(":", "").replace("-", "")[:15]
    fp = ROUNDS_DIR / f"round_{jid}_{round_no}_{ts}.json"
    fp.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                  encoding="utf-8")

    persisted = 0
    if persist:
        fresh = []
        for eid, rec in all_candidates.items():
            cls = classified.get(eid, "D")
            if eid in existing or cls not in ACCEPTED_CLASSES:
                continue
            out_rec = dict(rec)
            out_rec["relevant"] = cls in ("A1", "A2", "B")
            out_rec["relevance_score"] = out_rec.get("relevance_score", 0.0)
            meta = dict(out_rec.get("meta") or {})
            meta["acceptance_class"] = cls
            meta["discovered_by_round"] = round_id
            out_rec["meta"] = meta
            out_rec.setdefault("channel", "connector")
            fresh.append(out_rec)
        if fresh:
            corpus_fp = ROOT / "outputs" / f"round_{jid}_{round_no}_{ts}.jsonl"
            with corpus_fp.open("w", encoding="utf-8") as f:
                for r in fresh:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            persisted = len(fresh)
            record["persisted_documents"] = persisted
            record["persisted_file"] = corpus_fp.name
            fp.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    # 索引更新（与联邦轮同一视图）
    rounds: list[dict] = []
    for idx_fp in sorted(glob.glob(str(ROUNDS_DIR / "round_*.json"))):
        try:
            data = json.loads(Path(idx_fp).read_text(encoding="utf-8"))
            rounds.append({k: data.get(k) for k in
                           ("round_id", "scope_level", "accepted_novelty_rate",
                            "raw_yield", "totals", "ended_at", "plan_id",
                            "plan_hash", "round_mode", "round_validity")})
        except json.JSONDecodeError:
            continue
    plan_conv: dict[str, dict] = {}
    for h in sorted({r.get("plan_hash") for r in rounds if r.get("plan_hash")}):
        # 多管辖地并行：streak 只在**同 plan_hash 的轮次子集**内判定
        # （不同管辖地/不同 plan 的轮不得交错截断彼此的 streak）
        subset = [r for r in rounds if r.get("plan_hash") == h]
        plan_conv[h[:12]] = convergence_status(
            subset, plan_hash=h, mode_required="convergence_validation")
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({
        "generated_at": now_iso(), "rounds": rounds,
        "convergence": convergence_status(rounds),
        "plan_convergence": plan_conv}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return record


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="")
    ap.add_argument("--mode", default="discovery",
                    choices=["discovery", "validation"])
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--max-fetch", type=int, default=40)
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    if args.show:
        if INDEX.exists():
            data = json.loads(INDEX.read_text(encoding="utf-8"))
            print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        else:
            print("（尚无轮次索引）")
        return 0

    if not args.plan:
        print("❌ 管辖地轮必须 --plan <PLAN_ID>（如 SE_PLAN_V1）")
        return 2
    plan = load_plan(args.plan)
    for w in validate_plan(plan):
        print(f"  ⚠ {w}")
    jid = plan.jurisdiction
    if jid not in SUPPORTED:
        print(f"❌ 管辖地 {jid} 通道未适配（支持：{SUPPORTED}）——如实拒绝执行")
        return 2
    if plan.scope != jid:
        print(f"❌ 管辖地轮要求 scope == jurisdiction（{plan.scope} vs {jid}）")
        return 2
    print(f"▸ plan={plan.plan_id} hash={plan.plan_hash()[:12]} "
          f"jid={jid} mode={args.mode} routes={plan.discovery_routes}")
    record = await run_round(jid, args.round, plan, args.mode,
                             persist=not args.no_persist,
                             max_fetch=args.max_fetch)
    t = record["totals"]
    print(f"=== Round {record['round_id']} ===")
    print(f"  mode={record.get('round_mode')} "
          f"validity={record.get('round_validity')}")
    for r in record["routes"]:
        print(f"  [{r['id']}] {r['name']:26s} raw={r['raw_found']:4d} "
              f"uniq={r['unique_candidate_count']:4d} "
              f"new={r['new_unique_accepted_count']:3d} "
              f"dup={r['duplicate_accepted_count']:3d} "
              f"rej={r['rejected_count']:3d} fail={len(r['source_failures'])} "
              f"notfound={len(r.get('not_found') or [])} "
              f"｜ cls={r['accepted_by_class']}")
    print(f"  TOTAL raw={t['raw_found']} new_acc={t['new_unique_accepted_count']} "
          f"dup_acc={t['duplicate_accepted_count']} "
          f"failures={t['source_failures']}")
    print(f"  new_by_class={t.get('new_by_class', {})} "
          f"new_high_risk_B={t.get('new_high_risk_B', 0)}")
    print(f"  persisted={record.get('persisted_documents', 0)} → "
          f"{record.get('persisted_file', '（未写）')}")
    print(f"  raw_yield={record['raw_yield']}  ｜ accepted_novelty_rate="
          f"{record['accepted_novelty_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
