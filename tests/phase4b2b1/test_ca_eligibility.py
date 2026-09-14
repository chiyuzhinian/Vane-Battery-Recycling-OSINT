# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §6：US-CA eligibility 产物回归。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.search_plan import load_plan  # noqa: E402

LAYERS = ROOT / "outputs" / "audit" / "jurisdiction_layers.json"
CONTRACTS = ROOT / "outputs" / "audit" / "jurisdiction_contracts.json"


def test_ca_plan_v2_frozen_and_routes():
    plan = load_plan("US_CA_PLAN_V2")
    assert plan.plan_hash().startswith("9ab375a053ba")
    assert set(plan.discovery_routes) >= {"A", "C", "D"}
    # D 种子为实测存在的主法条直链（非换词）
    assert plan.query_set.cross_terms
    for seed in plan.query_set.cross_terms:
        assert ":" in seed  # LAW:SECTION 形态


def test_ca_contract_min_6_of_8():
    if not CONTRACTS.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_contracts.py")
    d = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    ca = next(c for c in d["contracts"] if c["jurisdiction_id"] == "US-CA")
    assert ca["covered_roles"] >= 6
    roles = {r["role"]: r for r in ca["roles"]}
    assert roles["STATE_ADMIN_CODE"]["covered"], "ADMIN_CODE 应由 CalRecycle 承接"
    assert roles["STATE_TRANSPORT_HAZMAT"].get("covered") in (True, False)


def test_ca_eligible_with_gates():
    if not LAYERS.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_layers.py")
    d = json.loads(LAYERS.read_text(encoding="utf-8"))
    ca = d["jurisdictions"]["US-CA"]
    assert ca["state"] == "JURISDICTION_CONVERGENCE_ELIGIBLE"
    assert ca["checks"]["critical_roles_100"] is True
    assert ca["checks"]["mandatory_coverage_min"] is True
    assert ca["checks"]["route_families_min_3"] is True
    assert ca["checks"]["identity_min_90"] is True
    assert ca["checks"]["no_unresolved_critical_failure"] is True
