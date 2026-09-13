# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 1：Source Role eligibility 硬闸门测试。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.convergence_layers import (  # noqa: E402
    CRITICAL_ROLES_BY_LEVEL, IDENTITY_MIN_PCT, MANDATORY_MIN, ROUTES_MIN,
    evaluate_jurisdiction, route_families,
)


def _base(covered: int, total: int, level: str = "member_state",
          crit_ok: bool = True, routes=("A", "B", "C"), ident: float = 95.0,
          failures=None) -> dict:
    if level == "member_state":
        crit = CRITICAL_ROLES_BY_LEVEL["member_state"]
    else:
        crit = CRITICAL_ROLES_BY_LEVEL["state"]
    roles = [{"role": r, "covered": crit_ok,
              "channels": [{"status": "CONNECTED",
                            "discovery_layer_only": False}]} for r in crit]
    return {"level": level, "mandatory_roles": total, "covered_roles": covered,
            "roles": roles}, dict(
        jid="X", level=level, plan_convergence={"converged": True, "streak": 2},
        rounds=[{"route_ids": list(routes)}], identity_pct=ident,
        unresolved_critical_failures=failures or [])


def test_mandatory_thresholds_member_state():
    c, kw = _base(covered=5, total=7)
    assert evaluate_jurisdiction(contract=c, **kw)["checks"][
        "mandatory_coverage_min"] is True
    c, kw = _base(covered=4, total=7)
    assert evaluate_jurisdiction(contract=c, **kw)["checks"][
        "mandatory_coverage_min"] is False


def test_mandatory_thresholds_state():
    c, kw = _base(covered=6, total=8, level="state")
    assert evaluate_jurisdiction(contract=c, **kw)["checks"][
        "mandatory_coverage_min"] is True
    c, kw = _base(covered=5, total=8, level="state")
    assert evaluate_jurisdiction(contract=c, **kw)["checks"][
        "mandatory_coverage_min"] is False


def test_critical_missing_role_fails():
    c, kw = _base(covered=7, total=7, crit_ok=False)
    r = evaluate_jurisdiction(contract=c, **kw)
    assert r["checks"]["critical_roles_100"] is False
    assert r["jurisdiction_eligible"] is False


def test_route_families_dedupe_and_merge():
    rounds = [{"route_ids": ["A", "A"]}, {"routes": [{"id": "B"}, {"id": "A"}]},
              {"route_ids": ["C"]}]
    assert route_families(rounds) == ["A", "B", "C"]
    assert ROUTES_MIN == 3
    # 同一路线重跑多轮只算 1 类
    assert route_families([{"route_ids": ["B"]}, {"route_ids": ["B"]}]) == ["B"]


def test_routes_below_three_fails():
    c, kw = _base(covered=7, total=7, routes=("B", "C"))
    r = evaluate_jurisdiction(contract=c, **kw)
    assert r["checks"]["route_families_min_3"] is False
    assert r["route_families"] == ["B", "C"]


def test_identity_threshold_boundary():
    c, kw = _base(covered=7, total=7, ident=IDENTITY_MIN_PCT)
    assert evaluate_jurisdiction(contract=c, **kw)["checks"][
        "identity_min_90"] is True
    c, kw = _base(covered=7, total=7, ident=89.9)
    assert evaluate_jurisdiction(contract=c, **kw)["checks"][
        "identity_min_90"] is False


def test_unresolved_critical_failure_blocks():
    c, kw = _base(covered=7, total=7,
                  failures=[{"jurisdiction": "X", "doc": "d1",
                             "error": "ConnectorBlocked"}])
    r = evaluate_jurisdiction(contract=c, **kw)
    assert r["checks"]["no_unresolved_critical_failure"] is False
    assert r["jurisdiction_eligible"] is False


def test_mandatory_min_constants():
    assert MANDATORY_MIN == {"member_state": 5, "state": 6}
    assert CRITICAL_ROLES_BY_LEVEL["member_state"] == (
        "MS_LEGISLATION_DATABASE", "MS_OFFICIAL_GAZETTE")
    assert CRITICAL_ROLES_BY_LEVEL["state"] == (
        "STATE_LEGISLATURE", "STATE_STATUTES")
