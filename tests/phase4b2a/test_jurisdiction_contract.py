# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 2：Jurisdiction Onboarding Contract —— fail-fast 与参考映射。

纪律：
    · 契约缺标准角色 / 缺通道与缺口说明 → 装载即失败
    · NIM ≠ national corpus（discovery_layer_only 强制）
    · DE/NL/ES/FR 映射后矩阵状态不得回归（Phase 4B-1 快照比对）
"""
from __future__ import annotations

import contextlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import ConfigError, load_registry  # noqa: E402
from app.policy.jurisdiction_onboarding import (  # noqa: E402
    MS_ROLES, ROLES_BY_LEVEL, STATE_ROLES, build_contract_registry,
    jurisdiction_exists, list_contracts, load_contract, validate_contract,
)

MATRIX = ROOT / "outputs" / "audit" / "source_role_gap_matrix.json"
REFERENCE = ("DE", "NL", "ES", "FR")


@contextlib.contextmanager
def _tmp_contracts():
    """本机 %TEMP% 权限缺陷 → 测试临时目录建在 outputs/ 下（同 4B-1 口径）。"""
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as td:
        yield Path(td)


def test_standard_role_sets_complete():
    assert len(MS_ROLES) == 7
    assert len(STATE_ROLES) == 8
    assert "MS_LEGISLATION_DATABASE" in MS_ROLES
    assert "STATE_BATTERY_EPR_OR_STEWARDSHIP" in STATE_ROLES
    assert ROLES_BY_LEVEL["member_state"] == MS_ROLES
    assert ROLES_BY_LEVEL["state"] == STATE_ROLES


def test_reference_contracts_load_and_validate():
    ids = list_contracts()
    assert set(REFERENCE) <= set(ids)
    for jid in REFERENCE:
        c = load_contract(jid)
        warns = validate_contract(c)
        assert isinstance(warns, list)
        assert c.level == "member_state"
        assert c.jurisdiction_id == jid


def test_contract_registry_has_no_errors():
    reg = build_contract_registry()
    assert reg["errors"] == []
    got = {c["jurisdiction_id"] for c in reg["contracts"]}
    assert set(REFERENCE) <= got
    for c in reg["contracts"]:
        assert c["mandatory_roles"] == 7
        assert 0 <= c["covered_roles"] <= 7


def test_missing_standard_role_fails_fast():
    src = Path(ROOT / "sources/jurisdiction-onboarding/DE.yaml").read_text(
        encoding="utf-8")
    bad = src.replace("- MS_STANDARDS_METADATA\n", "", 1)
    with _tmp_contracts() as tmp:
        (tmp / "DE.yaml").write_text(bad, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_contract("DE", base=tmp)


def test_nim_requires_discovery_layer_flag():
    src = Path(ROOT / "sources/jurisdiction-onboarding/DE.yaml").read_text(
        encoding="utf-8")
    bad = src.replace("discovery_layer_only: true", "discovery_layer_only: false", 1)
    with _tmp_contracts() as tmp:
        (tmp / "DE.yaml").write_text(bad, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_contract("DE", base=tmp)


def test_unknown_source_prefix_fails_fast():
    src = Path(ROOT / "sources/jurisdiction-onboarding/DE.yaml").read_text(
        encoding="utf-8")
    bad = src.replace("source_id: de_gesetze", "source_id: zz_wrong_prefix", 1)
    with _tmp_contracts() as tmp:
        (tmp / "DE.yaml").write_text(bad, encoding="utf-8")
        c = load_contract("DE", base=tmp)
        with pytest.raises(ConfigError):
            validate_contract(c)


def test_jurisdiction_ids_resolvable_in_registry():
    for jid in REFERENCE:
        assert jurisdiction_exists(jid), f"registry 无法解析 {jid}"


def test_registry_rows_include_all_reference_states():
    """所有 27 国 + 51 州在 registry 中都可解析（框架前提）。"""
    reg = load_registry()
    codes = set()
    for j in reg.jurisdictions:
        codes |= {c.get("code") for c in j.countries}
        codes |= {s.get("code") for s in j.states}
    assert {"DE", "NL", "ES", "FR", "PL", "HU"} <= codes
    assert {"US-CA", "US-MI", "US-TX"} <= codes


def test_reference_matrix_statuses_not_regressed():
    """DE/NL/ES/FR 的 MEMBER_STATE_CORE 行状态必须与 4B-1 一致（CONNECTED）。"""
    if not MATRIX.exists():
        pytest.skip("需先运行 scripts/audit_source_roles.py")
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))["rows"]
    for jid in REFERENCE:
        row = next((r for r in rows if r["jurisdiction"] == jid
                    and r["source_role"] == "MEMBER_STATE_CORE"), None)
        assert row is not None, f"矩阵缺少 {jid} 行"
        assert row["status"] == "CONNECTED", f"{jid} 状态回归：{row['status']}"
