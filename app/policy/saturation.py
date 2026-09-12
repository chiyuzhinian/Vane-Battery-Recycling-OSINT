# -*- coding: utf-8 -*-
"""Saturation Gate（Phase 4A §10）—— SG1–SG9 联合判定。

绝对禁止：audit exited 0 => SATURATED。
所有条件来自可复现审计（source_universe / goldset / legal_graph / identity）+
边际新颖度（feedback 引擎的 novel_rate，保留原闸门作为 SG8 一个条件）。
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

from app.policy.goldset import evaluate as eval_goldset
from app.policy.legal_graph import build_family_status
from app.policy.legal_identity import identity_completeness
from app.policy.source_universe import universe_summary

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "outputs"

THRESHOLDS = {
    "sg1_mandatory_covered_pct": 95.0,
    "sg1_critical_covered_pct": 100.0,
    "sg2_unresolved_failures": 0,
    "sg3_core_recall": 0.98,
    "sg3_p0_recall": 1.00,
    "sg4_ab_precision": 0.97,
    "sg5_identity_pct": 99.0,
    "sg6_p0_unresolved": 0,
    "sg7_routes": 3,
    "sg8_novel_rate": 0.02,
    "sg8_consecutive_rounds": 2,
    "sg9_high_risk_gap": 0,
}

_CRITICAL_ROLES = {"EURLEX_PRIMARY", "FEDERAL_REGISTER", "EURLEX_NIM"}


def _load_records() -> list[dict]:
    rows: dict[str, dict] = {}
    for fp in glob.glob(str(OUT / "*.jsonl")):
        if Path(fp).name.startswith(("_", "review")):
            continue
        for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = r.get("evidence_id")
            if eid and eid not in rows:
                rows[eid] = r
    return list(rows.values())


def _novelty_stats() -> dict:
    """从 feedback_state.json / iteration_log 读边际新颖度。"""
    state = OUT / "feedback_state.json"
    if not state.exists():
        return {"available": False, "novel_rate": None, "consecutive_rounds": 0}
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"available": False, "novel_rate": None, "consecutive_rounds": 0}
    rounds = data.get("rounds") or []
    consec = 0
    for rnd in reversed(rounds):
        nr = rnd.get("novel_rate")
        if nr is not None and nr < THRESHOLDS["sg8_novel_rate"]:
            consec += 1
        else:
            break
    last = rounds[-1].get("novel_rate") if rounds else None
    return {"available": bool(rounds), "novel_rate": last,
            "consecutive_rounds": consec, "total_rounds": len(rounds)}


def _discovery_routes(records: list[dict], families) -> dict:
    """四条独立发现路线（同一 API 换关键词不算多条）。"""
    has_celex = any((r.get("meta") or {}).get("celex") for r in records)
    has_nim = any(str(r.get("source_id") or "").startswith("eu_nim_")
                  for r in records)
    has_keyword = any(r.get("source_id") == "eu_eurlex_keyword" for r in records)
    has_browser = any(r.get("channel") == "browser_capture" for r in records)
    has_family = any(s.found_relations for s in families)
    routes = {
        "A_official_enumeration": has_celex or has_nim,
        "B_fulltext_native_language": has_keyword,
        "C_legal_relation_expansion": bool(has_family),
        "D_open_web_browser": has_browser,
    }
    return {"routes": routes, "count": sum(routes.values())}


def status_from(passed: int, total: int, blocked_expected: int = 0) -> str:
    """状态映射（纯函数，供测试与审计共用）。

    ⚠️ 回归风险锁定：
      · 0 results / 未通过 → 绝不为 SATURATED
      · blocked（期望角色被阻断）→ BLOCKED（优先于一切）
    """
    if blocked_expected > 0:
        return "BLOCKED"
    if passed == total:
        return "SATURATED"
    if passed >= total - 1:
        return "NEAR_SATURATED"
    if passed >= total - 4:
        return "PARTIAL"
    return "WEAK"


def evaluate_saturation(region: str) -> dict:
    universe = universe_summary()
    records = [r for r in _load_records()
               if _region_match(r, region)]

    # SG1 / SG2
    cov = universe.get(region, {})
    mandatory_pct = cov.get("pct", 0.0)
    blocked = [b for b in universe["blocked"] if b["jurisdiction"] == region]
    critical_rows = [r for r in universe["rows"]
                     if r["jurisdiction"] == region
                     and r["source_role"] in _CRITICAL_ROLES and r["expected"]]
    critical_pct = (100.0 * sum(1 for r in critical_rows
                                if r["status"] in ("CONNECTED", "COMPLETE"))
                    / len(critical_rows)) if critical_rows else 100.0

    # SG3 / SG4
    gold = eval_goldset()
    core_recall = None
    p0_recall = None
    if gold["cases_found"]:
        a_stats = [c for c in gold["details"] if c.get("status") == "OK"
                   and c.get("expected") in ("A1", "A2")]
        core_recall = gold["recall"]                     # 简化：整体召回
        p0_recall = 1.0 if gold["fn"] == 0 else \
            round((gold["tp"]) / (gold["tp"] + gold["fn"]), 3)

    # SG5
    ident = identity_completeness(records)

    # SG6 / SG9
    families = build_family_status()
    fam_unresolved = sum(len(s.unresolved_relations) for s in families)

    # SG7
    routes = _discovery_routes(records, families)

    # SG8
    novelty = _novelty_stats()

    checks = {
        "SG1_source_universe": {
            "mandatory_pct": mandatory_pct,
            "critical_pct": critical_pct,
            "pass": (mandatory_pct >= THRESHOLDS["sg1_mandatory_covered_pct"]
                     and critical_pct >= THRESHOLDS["sg1_critical_covered_pct"]),
        },
        "SG2_source_health": {
            "blocked_mandatory": len([b for b in blocked if b["expected"]]),
            "pass": len([b for b in blocked if b["expected"]]) == 0,
        },
        "SG3_gold_recall": {
            "recall": core_recall, "p0_recall": p0_recall,
            "insufficient": gold["INSUFFICIENT_GOLDSET"],
            "pass": (core_recall is not None and not gold["INSUFFICIENT_GOLDSET"]
                     and core_recall >= THRESHOLDS["sg3_core_recall"]
                     and (p0_recall or 0) >= THRESHOLDS["sg3_p0_recall"]),
        },
        "SG4_precision": {
            "ab_precision": gold["precision"],
            "pass": gold["precision"] >= THRESHOLDS["sg4_ab_precision"],
        },
        "SG5_legal_identity": {
            "pct": ident["pct"],
            "pass": ident["pct"] >= THRESHOLDS["sg5_identity_pct"],
        },
        "SG6_legal_family": {
            "p0_unresolved": fam_unresolved,
            "pass": fam_unresolved <= THRESHOLDS["sg6_p0_unresolved"],
        },
        "SG7_discovery_routes": {
            **routes,
            "pass": routes["count"] >= THRESHOLDS["sg7_routes"],
        },
        "SG8_marginal_novelty": {
            **novelty,
            "pass": (novelty["available"]
                     and novelty["consecutive_rounds"]
                     >= THRESHOLDS["sg8_consecutive_rounds"]),
        },
        "SG9_high_risk_gap": {
            "count": fam_unresolved,          # 当前：P0 家族未解决即高风险缺口
            "pass": fam_unresolved == 0,
        },
    }
    passed = sum(1 for c in checks.values() if c["pass"])
    total = len(checks)
    status = status_from(passed, total,
                         len([b for b in blocked if b["expected"]]))

    return {"region": region, "status": status,
            "checks_passed": f"{passed}/{total}",
            "checks": checks, "thresholds": THRESHOLDS,
            "goldset": {k: v for k, v in gold.items() if k != "details"}}


def _region_match(record: dict, region: str) -> bool:
    sid = str(record.get("source_id") or "")
    if region == "EU":
        return (sid in ("eur_lex", "eu_eurlex_battery_reg", "eu_eurlex_keyword",
                        "eu_eurlex_elv", "eu_eurlex_waste_shipment",
                        "eu_eurlex_crm")
                or sid.startswith("eu_nim_") or record.get("region") == "EU")
    if region == "US":
        return sid.startswith("us_") or sid.startswith("browser_phmsa") \
            or sid.startswith("browser_bci") or sid.startswith("browser_calrecycle")
    return True
