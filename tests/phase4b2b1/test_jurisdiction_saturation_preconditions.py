# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §13/§14：saturation 前置条件与 scale-out gate。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.saturation_gates import (  # noqa: E402
    domain_gate, evaluate_scaleout_preconditions, evidence_gate,
)

ARTIFACT = ROOT / "outputs" / "audit" / "scaleout_readiness.json"


def test_domain_gate_zero_contradictions():
    assert domain_gate({"contradictions_count": 0})["ok"] is True
    assert domain_gate({"contradictions_count": 2})["ok"] is False


def test_precondition_requires_all_layers():
    row = {"jurisdiction_eligible": True,
           "checks": {"critical_roles_100": True},
           "route_families": ["A", "B", "C"], "identity_pct": 100.0,
           "unresolved_critical_failures": []}
    ok = evaluate_scaleout_preconditions(
        layers_row=row,
        evidence_summary={"A1": {"fulltext_pct": 100.0},
                          "A2": {"fulltext_pct": 100.0},
                          "B": {"fulltext_pct": 100.0, "clause_pct": 100.0}},
        domain_mismatches={"contradictions_count": 0},
        adapted_channels=5, eligible_count=3,
        a1_status="INSUFFICIENT_A1_GOLDSET", a1_verified=1)
    assert ok["all_pass"] is True
    assert ok["a1"]["recall_claimed"] is False    # 不冒充 A1 recall


def test_precondition_fails_with_evidence_gap():
    row = {"jurisdiction_eligible": True,
           "checks": {"critical_roles_100": True},
           "route_families": ["A", "B", "C"], "identity_pct": 100.0,
           "unresolved_critical_failures": []}
    bad = evaluate_scaleout_preconditions(
        layers_row=row,
        evidence_summary={"A1": {"fulltext_pct": 100.0},
                          "A2": {"fulltext_pct": 10.0},
                          "B": {"fulltext_pct": 90.0, "clause_pct": 90.0}},
        domain_mismatches={"contradictions_count": 0},
        adapted_channels=5, eligible_count=3,
        a1_status="INSUFFICIENT_A1_GOLDSET", a1_verified=1)
    assert bad["all_pass"] is False
    assert "evidence_completeness" in bad["failing"]


def test_real_scaleout_artifact_honest():
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_scaleout_gate.py")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert d["eligible_count"] >= 3
    assert d["channels_adapted"] >= 5
    assert d["domain_contradictions"] == 0
    # 若证据完整性未过 → 必须 NOT READY（不得降门槛）
    ev = evidence_gate({
        "A1": d["evidence"]["A1"], "A2": d["evidence"]["A2"],
        "B": d["evidence"]["B"]})
    if not ev["ok"]:
        assert d["verdict"] == "NOT READY"
    assert d["verdict"] in ("READY", "NOT READY")


def test_near_saturated_stays_false():
    """4B-2B 合并 SG 体系前，near_saturated 恒 False。"""
    fp = ROOT / "outputs" / "audit" / "jurisdiction_layers.json"
    if not fp.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_layers.py")
    d = json.loads(fp.read_text(encoding="utf-8"))
    for jid, row in d["jurisdictions"].items():
        assert row["near_saturated"] is False, jid
