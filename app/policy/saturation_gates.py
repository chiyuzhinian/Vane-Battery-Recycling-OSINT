# -*- coding: utf-8 -*-
"""Saturation & Scale-Out Preconditions —— Phase 4B-2B1 §13/§14。

纪律：
  · 不修改历史 SG1–SG9 定义（4A 口径）；
  · 本模块提供 **precondition 明细**（供 near-saturation 与 scale-out
    判定引用）：EVIDENCE_COMPLETENESS_GATE / DOMAIN_CONSISTENCY_GATE
    等作为新增前置条件；
  · near_saturated 仍恒 False 至 4B-2B 合并 SG 体系——本模块只做
    **可评估**，不做放松。
"""
from __future__ import annotations

HIGH_VALUE_CLASSES = ("A1", "A2", "B")
FULLTEXT_MIN_PCT = 95.0
CLAUSE_MIN_PCT = 95.0


def evidence_gate(summary: dict) -> dict:
    """EVIDENCE_COMPLETENESS_GATE：A1/A2/B 全文率与 B 条款证据率 ≥95%。"""
    missing: list[str] = []
    detail: dict = {}
    for cls in HIGH_VALUE_CLASSES:
        s = summary.get(cls) or {}
        pct = float(s.get("fulltext_pct") or 0.0)
        detail[cls] = pct
        if pct < FULLTEXT_MIN_PCT:
            missing.append(f"{cls}_fulltext={pct}%")
    b_clause = float((summary.get("B") or {}).get("clause_pct") or 0.0)
    if b_clause < CLAUSE_MIN_PCT:
        missing.append(f"B_clause={b_clause}%")
    return {"ok": not missing, "fulltext_pct": detail,
            "b_clause_pct": b_clause, "missing": missing}


def domain_gate(mismatches: dict) -> dict:
    """DOMAIN_CONSISTENCY_GATE：语义矛盾 = 0。"""
    n = int(mismatches.get("contradictions_count") or 0)
    return {"ok": n == 0, "contradictions": n}


def evaluate_scaleout_preconditions(*, layers_row: dict, evidence_summary: dict,
                                    domain_mismatches: dict,
                                    adapted_channels: int,
                                    eligible_count: int,
                                    a1_status: str,
                                    a1_verified: int) -> dict:
    """单管辖地 + 全局的 Scale-out / near-saturation 前置条件评估。

    "A1 状态可解释"= 允许 INSUFFICIENT_A1_GOLDSET（只要不冒充 recall）。
    """
    checks = {
        "jurisdiction_eligible": bool(layers_row.get("jurisdiction_eligible")),
        "critical_roles_100": bool(
            (layers_row.get("checks") or {}).get("critical_roles_100")),
        "route_families_min_3": len(layers_row.get("route_families") or []) >= 3,
        "identity_min_90": float(layers_row.get("identity_pct") or 0) >= 90.0,
        "no_unresolved_critical_failure": not (
            layers_row.get("unresolved_critical_failures") or []),
        "evidence_completeness": evidence_gate(evidence_summary),
        "domain_consistency": domain_gate(domain_mismatches),
        "channels_adapted_min_5": adapted_channels >= 5,
        "eligible_min_3": eligible_count >= 3,
        "a1_explainable": a1_status in ("OK", "INSUFFICIENT_A1_GOLDSET"),
    }
    hard = {k: v for k, v in checks.items()
            if k not in ("evidence_completeness", "domain_consistency")}
    gate_detail = {"evidence_completeness": checks["evidence_completeness"],
                   "domain_consistency": checks["domain_consistency"]}
    all_pass = all(
        (v.get("ok") if isinstance(v, dict) else bool(v))
        for v in checks.values())
    failing = [k for k, v in checks.items()
               if not (v.get("ok") if isinstance(v, dict) else bool(v))]
    return {
        "checks": {**{k: v for k, v in hard.items()}, **gate_detail},
        "all_pass": all_pass,
        "failing": failing,
        "a1": {"status": a1_status, "verified": a1_verified,
               "recall_claimed": False},   # 不冒充 A1 recall
        "note": ("INSUFFICIENT_A1_GOLDSET 不阻塞开发，但必须阻止 A1 recall 声称。"
                 "near_saturated 仍恒 False 至 4B-2B 合并 SG 体系。"),
    }


def aggregate_eligible(preconditions: dict[str, dict]) -> dict:
    """Phase 4B-2B §2：eligible 全集逐一评估的聚合（禁止样本代表）。

    preconditions: {jid: evaluate_scaleout_preconditions(...)}（仅 eligible 者）。
    任何 eligible 自身 Gate 未通过 → 不得计入 eligible_pass。
    """
    total = len(preconditions)
    passed = sorted(j for j, r in preconditions.items() if r.get("all_pass"))
    failed = sorted(j for j, r in preconditions.items()
                    if not r.get("all_pass"))
    return {
        "eligible_total": total,
        "eligible_pass": len(passed),
        "eligible_fail": len(failed),
        "pass_list": passed,
        "fail_list": failed,
        "all_eligible_pass": total > 0 and not failed,
    }
