# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 1：plan 收敛 ≠ 管辖地 eligible（防误读核心测试）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.convergence_layers import (  # noqa: E402
    STATE_ELIGIBLE, STATE_NOT_CONVERGED, STATE_PLAN_CONVERGED,
    evaluate_jurisdiction,
)

ARTIFACT = ROOT / "outputs" / "audit" / "jurisdiction_layers.json"


def _contract(level_roles: dict[str, dict]) -> dict:
    roles = []
    covered = 0
    for role, chans in level_roles.items():
        ok = bool(chans)
        covered += 1 if ok else 0
        roles.append({"role": role, "covered": ok, "gap": "",
                      "channels": chans})
    return {"jurisdiction_id": "XX", "level": "member_state",
            "mandatory_roles": 7, "covered_roles": covered, "roles": roles}


def _ch(status="CONNECTED", discovery=False) -> dict:
    return {"source_id": "x", "status": status, "access_method": "html",
            "discovery_layer_only": discovery}


PLAN_OK = {"converged": True, "streak": 2}


def test_plan_converged_never_implies_eligible():
    """核心：plan streak=2 但角色覆盖 0/7 → 只能标 SOURCE_PLAN_CONVERGED。"""
    r = evaluate_jurisdiction(
        jid="SE", level="member_state",
        contract={"level": "member_state", "mandatory_roles": 7,
                  "covered_roles": 0, "roles": []},
        plan_convergence=PLAN_OK, rounds=[{"route_ids": ["B", "C"]}],
        identity_pct=100.0)
    assert r["plan_converged"] is True
    assert r["jurisdiction_eligible"] is False
    assert r["state"] == STATE_PLAN_CONVERGED
    assert r["near_saturated"] is False          # 恒 False（SG 未合并）


def test_eligible_requires_all_gates():
    crit = {"MS_LEGISLATION_DATABASE": [_ch()],
            "MS_OFFICIAL_GAZETTE": [_ch()]}
    contract = _contract(crit)
    contract["covered_roles"] = 5                    # 5/7 达标
    r = evaluate_jurisdiction(
        jid="SE", level="member_state", contract=contract,
        plan_convergence=PLAN_OK,
        rounds=[{"route_ids": ["A", "B", "C"]}], identity_pct=95.0)
    assert r["jurisdiction_eligible"] is True
    assert r["state"] == STATE_ELIGIBLE
    assert r["near_saturated"] is False              # 仍需 SG 体系


def test_nim_discovery_channel_not_counted_for_critical():
    """公报通道仅 NIM（discovery-layer）→ critical 不得算 100%。"""
    contract = {"level": "member_state", "mandatory_roles": 7,
                "covered_roles": 5,
                "roles": [
                    {"role": "MS_LEGISLATION_DATABASE",
                     "covered": True, "channels": [_ch()]},
                    {"role": "MS_OFFICIAL_GAZETTE", "covered": True,
                     "channels": [_ch(status="DISCOVERED", discovery=True)]},
                ]}
    r = evaluate_jurisdiction(
        jid="SE", level="member_state", contract=contract,
        plan_convergence=PLAN_OK,
        rounds=[{"route_ids": ["A", "B", "C"]}], identity_pct=95.0)
    assert r["checks"]["critical_roles_100"] is False
    assert r["jurisdiction_eligible"] is False


def test_not_converged_without_plan():
    r = evaluate_jurisdiction(
        jid="DE", level="member_state", contract=None,
        plan_convergence=None, rounds=[], identity_pct=0.0)
    assert r["state"] == STATE_NOT_CONVERGED
    assert r["jurisdiction_eligible"] is False


def test_real_pilots_plan_converged_but_not_eligible():
    """真实产物：四 pilot plan_converged=True；FI 因覆盖/路线不足不 eligible；
    US-WA（2B0 Step 6）、US-CA（2B1 §6）、SE（2B1 §7）已达成 eligible。"""
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_layers.py")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    js = d["jurisdictions"]
    for jid in ("FI",):
        assert js[jid]["plan_converged"] is True, jid
        assert js[jid]["jurisdiction_eligible"] is False, \
            f"{jid} 不得在覆盖/routes 不足时 eligible"
        assert js[jid]["state"] == STATE_PLAN_CONVERGED, jid
    # US-WA / US-CA / SE：eligible（全闸门过）或（若数据变化）至少 plan 收敛
    for jid in ("US-WA", "US-CA", "SE"):
        assert js[jid]["plan_converged"] is True, jid
        if js[jid]["jurisdiction_eligible"]:
            assert js[jid]["state"] == STATE_ELIGIBLE, jid
            assert len(js[jid]["route_families"]) >= 3, jid
    # 参考管辖地无 plan → NOT_CONVERGED
    for jid in ("DE", "NL", "ES", "FR"):
        assert js[jid]["state"] == STATE_NOT_CONVERGED, jid
    assert d["summary"]["near_saturated"] == 0
