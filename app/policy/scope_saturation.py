# -*- coding: utf-8 -*-
"""Scope-level Saturation（Phase 4B-1 Step 10 §13）—— 纯逻辑。

四个 scope 独立评价（禁止把 US Federal 当 "United States complete"）：
    EU_SUPRANATIONAL ｜ EU_MEMBER_STATES ｜ US_FEDERAL ｜ US_STATES

输入产物：
    outputs/audit/source_role_gap_matrix.json   （SG1 用新矩阵口径）
    outputs/fr_identity_overlay.jsonl           （US 身份富化）
    outputs/audit/discovery_rounds.json         （SG8 轮次）
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "outputs"

SCOPES = ("EU_SUPRANATIONAL", "EU_MEMBER_STATES", "US_FEDERAL", "US_STATES")

_SCOPE_REGION = {
    "EU_SUPRANATIONAL": "EU", "EU_MEMBER_STATES": "EU",
    "US_FEDERAL": "US", "US_STATES": "US",
}

#: 非 supra/federal 分分母的角色（防止把州级/成员国混入联邦口径）
SUB_NATIONAL_ROLES = {
    "MEMBER_STATE_LEGISLATION", "MEMBER_STATE_OFFICIAL_GAZETTE", "MEMBER_STATE_CORE",
    "STATE_LEGISLATION", "STATE_ADMIN_RULES", "STATE_ENVIRONMENT_AGENCY",
    "STATE_EPR_PROGRAM", "STATE_CORE",
}


def _matrix_rows() -> list[dict]:
    fp = OUT / "audit" / "source_role_gap_matrix.json"
    if not fp.exists():
        return []
    try:
        return json.loads(fp.read_text(encoding="utf-8")).get("rows") or []
    except json.JSONDecodeError:
        return []


def scope_universe(scope: str) -> dict:
    """SG1：从**新矩阵**读取该 scope 的 mandatory/critical 覆盖。"""
    rows = [r for r in _matrix_rows() if r.get("scope") == scope]
    if not rows:
        return {"available": False, "mandatory_pct": 0.0, "critical_pct": 0.0,
                "mandatory": {"total": 0, "covered": 0},
                "critical": {"total": 0, "covered": 0}}
    covered = ("CONNECTED", "COMPLETE")
    if scope in ("EU_SUPRANATIONAL", "US_FEDERAL"):
        m = [r for r in rows if r.get("mandatory")
             and r.get("source_role") not in SUB_NATIONAL_ROLES]
        c = [r for r in rows if r.get("critical")]
    else:
        m = c = rows
    def pct(rs: list[dict]) -> float:
        if not rs:
            return 100.0
        return round(100.0 * sum(1 for r in rs if r["status"] in covered) / len(rs), 1)
    return {
        "available": True,
        "mandatory": {"total": len(m), "covered": sum(1 for r in m if r["status"] in covered)},
        "critical": {"total": len(c), "covered": sum(1 for r in c if r["status"] in covered)},
        "mandatory_pct": pct(m),
        "critical_pct": pct(c),
        "blocked": [r["source_role"] for r in m if r["status"] == "BLOCKED"],
        "open_roles": [{"role": r["source_role"], "status": r["status"]}
                       for r in m if r["status"] not in covered],
    }


def scope_identity(records: list[dict], scope: str) -> dict:
    """SG5：scope 内记录身份完整度（US 侧自动合并 FR 富化）。"""
    from app.policy.backfill import load_jsonl, record_completeness
    region = _SCOPE_REGION.get(scope, "")
    scoped = [r for r in records if _region_of(r) == region]
    if scope in ("US_FEDERAL", "US_STATES"):
        rows = load_jsonl(OUT / "fr_identity_overlay.jsonl")
        fr = {eid: row["fr_identity"] for eid, row in rows.items()
              if row.get("fr_identity")}
        return record_completeness(scoped, fr_identities=fr)
    return record_completeness(scoped)


def scope_routes(records: list[dict], scope: str) -> dict:
    """SG7：独立发现路线数（本 scope）。"""
    region = _SCOPE_REGION.get(scope, "")
    scoped = [r for r in records if _region_of(r) == region]
    has_enum = any((r.get("meta") or {}).get("celex") for r in scoped) or \
        any(str(r.get("source_id", "")).startswith(("us_frc", "eu_nim", "us_ecfr"))
            for r in scoped)
    has_keyword = any(str(r.get("source_id")) == "eu_eurlex_keyword" for r in scoped) \
        or any(str((r.get("meta") or {}).get("discovered_by") or "") for r in scoped)
    has_family = False
    fam = OUT / "audit" / "legal_family_official.json"
    if fam.exists():
        try:
            has_family = bool(json.loads(fam.read_text(encoding="utf-8")).get("roots"))
        except json.JSONDecodeError:
            has_family = False
    has_browser = any(str(r.get("channel")) == "browser_capture" for r in scoped)
    routes = {"A_official_enumeration": has_enum,
              "B_fulltext_native_language": has_keyword,
              "C_legal_relation_expansion": has_family,
              "D_open_web_browser": has_browser}
    return {"routes": routes, "count": sum(routes.values())}


def scope_novelty(scope: str) -> dict:
    """SG8：该 scope 的轮次收敛状态。

    Phase 4B-2A 协议：优先按 **plan 绑定** 计算——
    同一 plan_hash 的 MODE B（convergence_validation）+ FULL 轮次才可计数；
    无任何 plan 绑定的轮次（如 4B-1 历史）退化为 legacy 视图并显式标记
    `plan_bound=False`（不得伪称已按新协议验证）。
    """
    from app.policy.rounds import convergence_status
    idx = OUT / "audit" / "discovery_rounds.json"
    if not idx.exists():
        return {"available": False, "novel_rate": None, "consecutive_rounds": 0}
    try:
        data = json.loads(idx.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"available": False, "novel_rate": None, "consecutive_rounds": 0}
    rounds = [r for r in (data.get("rounds") or [])
              if r.get("scope_level") == scope]
    if not rounds:
        return {"available": False, "novel_rate": None, "consecutive_rounds": 0}
    plan_rounds = [r for r in rounds if r.get("plan_hash")]
    if plan_rounds:
        latest_hash = plan_rounds[-1].get("plan_hash")
        conv = convergence_status(rounds, plan_hash=latest_hash,
                                  mode_required="convergence_validation")
        last = [r for r in rounds if r.get("plan_hash") == latest_hash][-1]
        return {"available": True, "novel_rate": last.get("accepted_novelty_rate"),
                "consecutive_rounds": conv["streak"], "total_rounds": len(rounds),
                "plan_rounds": len([r for r in rounds
                                    if r.get("plan_hash") == latest_hash]),
                "converged": conv["converged"],
                "blocked_by_high_value": conv["blocked_by_high_value"],
                "blocked_reason": conv.get("blocked_reason", ""),
                "plan_id": last.get("plan_id", ""),
                "plan_hash": (latest_hash or "")[:12],
                "plan_bound": True,
                "raw_yield": last.get("raw_yield"),
                "metric": "accepted_novelty_rate"}
    # legacy 视图（4B-1 历史：无 plan 绑定，如实标记）
    conv = convergence_status(rounds)
    return {"available": True, "novel_rate": rounds[-1].get("accepted_novelty_rate"),
            "consecutive_rounds": conv["streak"], "total_rounds": len(rounds),
            "converged": conv["converged"], "plan_bound": False,
            "raw_yield": rounds[-1].get("raw_yield"),
            "metric": "accepted_novelty_rate"}


def _region_of(record: dict) -> str:
    from app.policy.backfill import region_of
    return region_of(record)
