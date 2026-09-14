# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §7：EU pilot（SE/FI）eligibility 产物回归。"""
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


def test_se_plan_v2_frozen_and_routes():
    plan = load_plan("SE_PLAN_V2")
    assert plan.plan_hash().startswith("b22caa0377a2")
    assert set(plan.discovery_routes) >= {"A", "B", "C"}


def test_se_contract_min_5_of_7():
    if not CONTRACTS.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_contracts.py")
    d = json.loads(CONTRACTS.read_text(encoding="utf-8"))
    se = next(c for c in d["contracts"] if c["jurisdiction_id"] == "SE")
    assert se["covered_roles"] >= 5
    roles = {r["role"]: r for r in se["roles"]}
    assert roles["MS_TRANSPORT_OR_DANGEROUS_GOODS"]["covered"]
    assert roles["MS_STANDARDS_METADATA"]["covered"]


def test_se_eligible_with_gates():
    if not LAYERS.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_layers.py")
    d = json.loads(LAYERS.read_text(encoding="utf-8"))
    se = d["jurisdictions"]["SE"]
    assert se["state"] == "JURISDICTION_CONVERGENCE_ELIGIBLE"
    assert se["checks"]["critical_roles_100"] is True
    assert se["checks"]["mandatory_coverage_min"] is True
    assert se["checks"]["route_families_min_3"] is True
    assert se["checks"]["identity_min_90"] is True


def test_fi_honestly_not_eligible():
    """FI 覆盖不足 → 如实不 eligible（不得为凑数注册无采集能力角色）。"""
    if not LAYERS.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_layers.py")
    d = json.loads(LAYERS.read_text(encoding="utf-8"))
    fi = d["jurisdictions"]["FI"]
    assert fi["state"] == "SOURCE_PLAN_CONVERGED"
    assert fi["jurisdiction_eligible"] is False


def test_eligible_total_reaches_three():
    if not LAYERS.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_layers.py")
    d = json.loads(LAYERS.read_text(encoding="utf-8"))
    eligible = [j for j, r in d["jurisdictions"].items()
                if r["jurisdiction_eligible"]]
    assert len(eligible) >= 3
    assert {"SE", "US-CA", "US-WA"} <= set(eligible)
