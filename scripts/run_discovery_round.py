# -*- coding: utf-8 -*-
"""run_discovery_round.py —— LIVE Discovery Round 执行器。

Phase 4B-2A Step 1 协议（搜索空间版本化）：
    · 新轮次必须 `--plan <PLAN_ID>`（sources/search-plans/*.yaml）
      → 轮次绑定 plan_id + plan_hash；搜索空间任何变化必须新 plan（reset）
    · `--mode discovery` = MODE A（扩张，不入 SG8）
      `--mode validation` = MODE B（冻结验证；禁止改 routes/词表）
    · 无 --plan 时退化为 legacy（仅复现历史，不参与新协议 streak）
    · 瞬态网络失败自动重试 1 次；重试恢复记 transient；仍失败按 taxonomy 入档
    · 每轮输出 round_validity（FULL/PARTIAL/INVALID）与 new_by_class / new_high_risk_B

4 条独立路线（同一 API 换关键词不算独立）：
    A 官方枚举     ：FR 机构枚举（无关键词）／EUR-Lex CELEX 年段枚举（plan 冻结）
    B 母语全文检索 ：FR 引号短语 ／EUR-Lex 关键词
    C 法律关系扩张 ：官方家族关系成员（Cellar 产物）→ 按 CELEX 回采
    D 开放网缺口   ：CROSS 检索 ／ Basel 出版物页（官方站点）

用法：
    py scripts/run_discovery_round.py --plan US_FED_PLAN_V1 --mode discovery --round 1
    py scripts/run_discovery_round.py --plan EU_SUPRA_PLAN_V1 --mode validation --round 1
    py scripts/run_discovery_round.py --show          # 查看轮次索引与收敛状态

产物：
    outputs/discovery_rounds/round_{scope}_{n}_{ts}.json
    outputs/audit/discovery_rounds.json（索引：legacy 视图 + plan_convergence 严格视图）
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.backfill import load_records  # noqa: E402
from app.policy.rounds import (  # noqa: E402
    RouteResult, build_round_record, convergence_status, derive_validity, now_iso,
)
from app.policy.search_plan import load_plan, validate_plan  # noqa: E402

ROUNDS_DIR = ROOT / "outputs" / "discovery_rounds"
INDEX = ROOT / "outputs" / "audit" / "discovery_rounds.json"
FAMILY = ROOT / "outputs" / "audit" / "legal_family_official.json"
FR_LINKS = ROOT / "outputs" / "audit" / "fr_cfr_links.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

#: LEGACY 查询集（Phase 4B-1 遗留：**按轮号换词** —— 实验设计缺陷已废止）
#: 仅用于无 plan 的 legacy 复现；新轮次必须走 sources/search-plans/*.yaml
LEGACY_QUERY_SETS = {
    1: {"fr_terms": ['"black mass"', '"battery recycling"', '"lithium battery"',
                     '"battery waste"'],
        "eu_keywords": ["black mass", "waste battery", "battery recycling"],
        "cross_terms": ["black mass", "battery waste", "battery recycling"]},
    2: {"fr_terms": ['"electric vehicle battery"', '"used batteries"',
                     '"battery materials"', '"lithium-ion"'],
        "eu_keywords": ["traction battery", "battery repurposing", "recycled content"],
        "cross_terms": ["lithium-ion", "battery materials", "energy storage"]},
    3: {"fr_terms": ['"batteries"', '"critical minerals"', '"battery"'],
        "eu_keywords": ["battery passport", "due diligence battery", "end-of-life vehicle"],
        "cross_terms": ["cathode", "recycling equipment", "battery packs"]},
}

FR_AGENCIES = ["environmental-protection-agency", "energy-department",
               "pipeline-and-hazardous-materials-safety-administration",
               "u-s-customs-and-border-protection", "industry-and-security-bureau"]

#: legacy 默认 CELEX 年段（R3 曾私下扩张 —— 新协议下必须新 plan）
LEGACY_CELEX_PREFIXES = ["32026R", "32026L"]


def _query_dict(plan, round_no: int) -> dict:
    """plan → 运行查询字典；plan 为空时回退 legacy（不推荐）。"""
    if plan is not None:
        qs = plan.query_set
        return {"fr_agencies": list(qs.fr_agencies),
                "fr_terms": list(qs.fr_terms),
                "eu_keywords": list(qs.eu_keywords),
                "cross_terms": list(qs.cross_terms),
                "basel_publications": bool(qs.basel_publications),
                "celex_prefixes": list(plan.year_segments)}
    q = dict(LEGACY_QUERY_SETS.get(round_no, LEGACY_QUERY_SETS[1]))
    q["fr_agencies"] = FR_AGENCIES
    q["celex_prefixes"] = LEGACY_CELEX_PREFIXES
    q["basel_publications"] = True
    return q


async def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=UA, timeout=45, follow_redirects=True)


async def _get(client: httpx.AsyncClient, url: str, *, params=None):
    """GET + 瞬态重试 1 次（退避 2s）。返回 (response, recovered)。

    仅对网络级异常（ConnectError/Timeout/RemoteProtocol 等）重试；
    4xx/5xx 属于源响应（不重试，按 taxonomy 记失败）。
    """
    try:
        return await client.get(url, params=params), False
    except Exception:  # noqa: BLE001 —— 网络瞬态
        await asyncio.sleep(2)
        return await client.get(url, params=params), True


def _fr_record(doc: dict, *, route: str) -> dict:
    return {
        "evidence_id": f"us_fr_{doc.get('document_number')}",
        "channel": "connector", "source_id": "us_federal_register", "region": "US",
        "url": doc.get("html_url"), "title": doc.get("title") or "",
        "publish_date": doc.get("publication_date") or "",
        "meta": {"region": "US", "document_number": doc.get("document_number"),
                 "type": doc.get("type"), "agencies": doc.get("agencies", []),
                 "collector": f"round_{route}"},
        "text": "\n".join(filter(None, [doc.get("title"), doc.get("abstract"),
                                        doc.get("excerpts")]))[:8000],
    }


async def route_a(client: httpx.AsyncClient, scope: str, q: dict) -> RouteResult:
    rr = RouteResult("A", "official_enumeration")
    if scope == "US_FEDERAL":
        for ag in q["fr_agencies"]:
            rr.queries.append(f"agency={ag}")
            try:
                r, recovered = await _get(
                    client,
                    "https://www.federalregister.gov/api/v1/documents.json",
                    params=[("conditions[agencies][]", ag),
                            ("per_page", "20"), ("order", "newest"),
                            ("fields[]", "title"), ("fields[]", "abstract"),
                            ("fields[]", "document_number"), ("fields[]", "type"),
                            ("fields[]", "publication_date"), ("fields[]", "html_url"),
                            ("fields[]", "agencies"), ("fields[]", "excerpts")])
                if recovered:
                    rr.transient_recovered += 1
                rr.source_success["us_federal_register"] = \
                    rr.source_success.get("us_federal_register", 0) + 1
                docs = r.json().get("results", [])
                rr.raw_found += len(docs)
                rr.candidates += [_fr_record(d, route="A") for d in docs]
            except Exception as exc:  # noqa: BLE001
                rr.source_failures.append({"source": "us_federal_register",
                                           "query": ag, "failure": type(exc).__name__})
    else:  # EU_SUPRANATIONAL：CELEX 年段枚举（年段来自 plan，必须冻结）
        from app.connectors.eur_lex import EurLexConnector
        conn = EurLexConnector()
        for prefix in (q.get("celex_prefixes") or LEGACY_CELEX_PREFIXES):
            rr.queries.append(f"celex={prefix}")
            try:
                evidences = await conn._fetch_by_celex(prefix, limit=25)
                rr.source_success["eur_lex"] = rr.source_success.get("eur_lex", 0) + 1
                rr.raw_found += len(evidences)
                for ev in evidences:
                    rr.candidates.append({
                        "evidence_id": ev.evidence_id, "channel": ev.channel,
                        "source_id": ev.source_id, "region": "EU",
                        "url": ev.source_url, "title": ev.source_title or "",
                        "publish_date": ev.publish_date.date().isoformat()
                        if ev.publish_date else "",
                        "meta": dict(ev.meta), "text": ev.raw_text[:8000]})
            except Exception as exc:  # noqa: BLE001
                rr.source_failures.append({"source": "eur_lex", "query": prefix,
                                           "failure": type(exc).__name__})
    return rr


async def route_b(client: httpx.AsyncClient, scope: str, q: dict) -> RouteResult:
    rr = RouteResult("B", "native_fulltext_search")
    if scope == "US_FEDERAL":
        for term in q["fr_terms"]:
            rr.queries.append(term)
            try:
                r, recovered = await _get(
                    client,
                    "https://www.federalregister.gov/api/v1/documents.json",
                    params=[("conditions[term]", term.replace('"', "")),
                            ("per_page", "20"), ("order", "newest"),
                            ("fields[]", "title"), ("fields[]", "abstract"),
                            ("fields[]", "document_number"), ("fields[]", "type"),
                            ("fields[]", "publication_date"), ("fields[]", "html_url"),
                            ("fields[]", "agencies"), ("fields[]", "excerpts")])
                if recovered:
                    rr.transient_recovered += 1
                rr.source_success["us_federal_register"] = \
                    rr.source_success.get("us_federal_register", 0) + 1
                docs = r.json().get("results", [])
                rr.raw_found += len(docs)
                rr.candidates += [_fr_record(d, route="B") for d in docs]
            except Exception as exc:  # noqa: BLE001
                rr.source_failures.append({"source": "us_federal_register",
                                           "query": term, "failure": type(exc).__name__})
    else:
        from app.connectors.eur_lex import EurLexConnector
        conn = EurLexConnector()
        for kw in q["eu_keywords"]:
            rr.queries.append(kw)
            try:
                evidences = await conn._fetch_by_keyword(kw, since="2024-01-01",
                                                         limit=25)
                rr.source_success["eur_lex"] = rr.source_success.get("eur_lex", 0) + 1
                rr.raw_found += len(evidences)
                for ev in evidences:
                    rr.candidates.append({
                        "evidence_id": ev.evidence_id, "channel": ev.channel,
                        "source_id": ev.source_id, "region": "EU",
                        "url": ev.source_url, "title": ev.source_title or "",
                        "publish_date": ev.publish_date.date().isoformat()
                        if ev.publish_date else "",
                        "meta": dict(ev.meta), "text": ev.raw_text[:8000]})
            except Exception as exc:  # noqa: BLE001
                rr.source_failures.append({"source": "eur_lex", "query": kw,
                                           "failure": type(exc).__name__})
    return rr


async def route_c(client: httpx.AsyncClient, scope: str, q: dict,
                  existing: set[str]) -> RouteResult:
    """法律关系扩张：官方家族成员（未入库）→ 回采。"""
    rr = RouteResult("C", "legal_relation_expansion")
    if not FAMILY.exists():
        rr.source_failures.append({"source": "cellar", "failure": "no_family_file"})
        return rr
    family = json.loads(FAMILY.read_text(encoding="utf-8")).get("roots", {})
    wanted: list[str] = []
    for root, entry in family.items():
        for rel in ("AMENDS", "CORRIGENDUM_OF", "REPEALS"):
            for row in (entry.get("relations", {}).get(rel) or []):
                celex = row.get("celex") or ""
                if celex and f"celex:{celex}" not in existing:
                    wanted.append(celex)
    wanted = sorted(set(wanted))[:12]
    rr.queries = [f"celex:{c}" for c in wanted[:10]]
    if not wanted:
        return rr
    from app.connectors.eur_lex import EurLexConnector
    conn = EurLexConnector()
    try:
        evidences = await conn.fetch_celex_batch(wanted, limit=200)
        rr.source_success["eur_lex"] = rr.source_success.get("eur_lex", 0) + 1
        rr.raw_found += len(evidences)
        for ev in evidences:
            rr.candidates.append({
                "evidence_id": ev.evidence_id, "channel": ev.channel,
                "source_id": ev.source_id, "region": "EU",
                "url": ev.source_url, "title": ev.source_title or "",
                "publish_date": ev.publish_date.date().isoformat()
                if ev.publish_date else "",
                "meta": dict(ev.meta), "text": ev.raw_text[:8000]})
    except Exception as exc:  # noqa: BLE001
        rr.source_failures.append({"source": "eur_lex", "query": "celex_batch",
                                   "failure": type(exc).__name__})
    return rr


async def route_d(client: httpx.AsyncClient, scope: str, q: dict,
                  existing: set[str]) -> RouteResult:
    rr = RouteResult("D", "open_web_gap_discovery")
    if scope == "US_FEDERAL":
        for term in q["cross_terms"]:
            rr.queries.append(f"cross:{term}")
            try:
                r, recovered = await _get(
                    client, "https://rulings.cbp.gov/api/search",
                    params=[("term", term)])
                if recovered:
                    rr.transient_recovered += 1
                rr.source_success["cbp_cross"] = \
                    rr.source_success.get("cbp_cross", 0) + 1
                payload = r.json()
                rulings = payload.get("rulings", [])
                rr.raw_found += len(rulings)
                from app.policy.us_trade import cross_record, parse_cross_rulings
                for ruling in parse_cross_rulings(payload, term=term):
                    rr.candidates.append(cross_record(ruling))
            except Exception as exc:  # noqa: BLE001
                rr.source_failures.append({"source": "cbp_cross", "query": term,
                                           "failure": type(exc).__name__})
    else:
        if not q.get("basel_publications", True):
            return rr
        rr.queries.append("basel:publications")
        try:
            r, recovered = await _get(
                client,
                "https://www.basel.int/Implementation/Publications/"
                "TechnicalGuidelines/tabid/2362/Default.aspx")
            if recovered:
                rr.transient_recovered += 1
            rr.source_success["basel"] = rr.source_success.get("basel", 0) + 1
            rr.raw_found += 1
            links = re.findall(r'href="([^"]*download\.aspx[^"]*)"', r.text)
            for i, link in enumerate(sorted(set(links))[:8]):
                url = link if link.startswith("http") else f"https://www.basel.int{link}"
                rr.candidates.append({
                    "evidence_id": f"int_basel_doc_{i}",
                    "channel": "connector", "source_id": "int_basel",
                    "region": "GLOBAL", "url": url,
                    "title": f"Basel Convention document ({url[-40:]})",
                    "publish_date": "",
                    "meta": {"region": "GLOBAL", "collector": "round_D",
                             "organization": "Basel Convention", "format": "pdf",
                             "fulltext_parseable": False},
                    "text": "Basel Convention publication (metadata only)"})
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": "basel", "query": "publications",
                                       "failure": type(exc).__name__})
    return rr


def _existing_ids() -> tuple[set[str], set[str]]:
    records = load_records(ROOT)
    ids = {str(r.get("evidence_id")) for r in records}
    celex = {f"celex:{(r.get('meta') or {}).get('celex')}"
             for r in records if (r.get("meta") or {}).get("celex")}
    return ids, celex


async def run_round(scope: str, round_no: int, routes: list[str],
                    *, persist: bool = True, plan=None, mode: str | None = None,
                    routes_override: bool = False) -> dict:
    q = _query_dict(plan, round_no)
    existing_ids, existing_celex = _existing_ids()
    started = now_iso()
    results: list[RouteResult] = []
    async with await _client() as client:
        if "A" in routes:
            results.append(await route_a(client, scope, q))
        if "B" in routes:
            results.append(await route_b(client, scope, q))
        if "C" in routes:
            results.append(await route_c(client, scope, q, existing_celex))
        if "D" in routes:
            results.append(await route_d(client, scope, q, existing_ids))

    # 逐条分类（acceptance）+ 主题（高风险 B 计数用），计算指标
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
    route_dicts = [rr.as_dict(classified=classified, existing_ids=existing_ids,
                              topics_by_id=topics_by_id) for rr in results]

    # ---- 失效判定（规格 §六）：critical 源失败且该源本轮零成功 → INVALID ----
    failures = [f for r in route_dicts for f in (r.get("source_failures") or [])]
    success: dict[str, int] = {}
    for r in route_dicts:
        for src, n in (r.get("source_success") or {}).items():
            success[src] = success.get(src, 0) + int(n)
    critical = set(plan.critical_sources) if plan is not None else set()
    crit_fail_no_success = any(
        (f.get("source") in critical) and success.get(f.get("source"), 0) == 0
        for f in failures)
    validity = derive_validity(failures=len(failures),
                               critical_failed_no_success=crit_fail_no_success)
    round_mode = mode or ("discovery_expansion" if plan is not None else "legacy")
    round_id = f"{scope}-R{round_no}-{now_iso()[:10]}"
    record = build_round_record(
        round_id=round_id, scope=scope, started_at=started, ended_at=now_iso(),
        routes=route_dicts,
        source_roles=[pr.role for pr in plan.source_roles] if plan else [],
        plan_id=plan.plan_id if plan else "",
        plan_hash=plan.plan_hash() if plan else "",
        round_mode=round_mode, validity=validity,
        transient_failures=sum(int(r.get("transient_recovered", 0) or 0)
                               for r in route_dicts),
        notes="routes_override=true（MODE A 扩张）" if routes_override else "")
    # 落盘
    ROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_iso().replace(":", "").replace("-", "")[:15]
    fp = ROUNDS_DIR / f"round_{scope}_{round_no}_{ts}.json"
    fp.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                  encoding="utf-8")

    # ★ 持久化：新入选文档写入语料（outputs/round_*.jsonl）
    #   否则下一轮会把同一批文档重复计为"新发现"，novelty 永不收敛（设计缺口修复）
    persisted = 0
    if persist:
        from app.policy.rounds import ACCEPTED_CLASSES
        fresh = []
        for eid, rec in all_candidates.items():
            cls = classified.get(eid, "D")
            if eid in existing_ids or cls not in ACCEPTED_CLASSES:
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
            corpus_fp = ROOT / "outputs" / f"round_{scope}_{round_no}_{ts}.jsonl"
            with corpus_fp.open("w", encoding="utf-8") as f:
                for r in fresh:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            persisted = len(fresh)
            record["persisted_documents"] = persisted
            record["persisted_file"] = corpus_fp.name
            fp.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    # 更新索引 + 收敛状态（双视图：legacy 全量 / plan 严格）
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
        plan_conv[h[:12]] = convergence_status(
            rounds, plan_hash=h, mode_required="convergence_validation")
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({
        "generated_at": now_iso(), "rounds": rounds,
        "convergence": convergence_status(rounds),
        "plan_convergence": plan_conv}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return record


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="",
                    choices=["", "US_FEDERAL", "EU_SUPRANATIONAL"])
    ap.add_argument("--plan", default="",
                    help="search-plan id（如 US_FED_PLAN_V1）；缺省 = legacy（不推荐）")
    ap.add_argument("--mode", default="", choices=["", "discovery", "validation"])
    ap.add_argument("--routes", default="A,B,C,D")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--no-persist", action="store_true",
                    help="不把新入选文档写入语料（默认写入）")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    if args.show:
        if INDEX.exists():
            data = json.loads(INDEX.read_text(encoding="utf-8"))
            print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        else:
            print("（尚无轮次索引）")
        return 0

    if args.plan:
        plan = load_plan(args.plan)
        for w in validate_plan(plan):
            print(f"  ⚠ {w}")
        scope = plan.scope
        mode_map = {"": "discovery_expansion",
                    "discovery": "discovery_expansion",
                    "validation": "convergence_validation"}
        mode = mode_map[args.mode]
        routes = args.routes.split(",")
        override = routes != list(plan.discovery_routes)
        if mode == "convergence_validation" and override:
            raise SystemExit(
                f"❌ MODE B 不允许改变搜索空间：plan routes={plan.discovery_routes} "
                f"vs --routes={routes}（如需扩张请用 MODE A + 新 plan）")
        print(f"▸ plan={plan.plan_id} hash={plan.plan_hash()[:12]} "
              f"mode={mode} validity将自动判定")
        record = await run_round(scope, args.round, routes,
                                 persist=not args.no_persist, plan=plan,
                                 mode=mode, routes_override=override)
    else:
        scope = args.scope or "US_FEDERAL"
        print("⚠ legacy 模式（无 plan 绑定）：不参与新协议 streak；"
              "建议 --plan <PLAN_ID>")
        record = await run_round(scope, args.round, args.routes.split(","),
                                 persist=not args.no_persist)
    t = record["totals"]
    print(f"=== Round {record['round_id']} ===")
    print(f"  plan={record.get('plan_id') or '（legacy）'} "
          f"mode={record.get('round_mode')} validity={record.get('round_validity')}")
    for r in record["routes"]:
        print(f"  [{r['id']}] {r['name']:26s} raw={r['raw_found']:4d} "
              f"uniq={r['unique_candidate_count']:4d} new={r['new_unique_accepted_count']:3d} "
              f"dup={r['duplicate_accepted_count']:3d} rej={r['rejected_count']:3d} "
              f"fail={len(r['source_failures'])} ｜ cls={r['accepted_by_class']}")
    print(f"  TOTAL raw={t['raw_found']} new_acc={t['new_unique_accepted_count']} "
          f"dup_acc={t['duplicate_accepted_count']} failures={t['source_failures']} "
          f"transient_recovered={t.get('transient_failures', 0)}")
    print(f"  new_by_class={t.get('new_by_class', {})} "
          f"new_high_risk_B={t.get('new_high_risk_B', 0)}")
    print(f"  persisted={record.get('persisted_documents', 0)} → "
          f"{record.get('persisted_file', '（未写）')}")
    print(f"  raw_yield={record['raw_yield']}  ｜ accepted_novelty_rate="
          f"{record['accepted_novelty_rate']}  ← SG8 主判据")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
