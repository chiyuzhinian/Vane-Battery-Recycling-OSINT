# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 1：Search Plan Versioning —— hash 稳定性与 fail-fast。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import ConfigError  # noqa: E402
from app.policy.search_plan import (  # noqa: E402
    SearchPlan, build_registry, load_plan, validate_plan,
)

BASE = {
    "version": 1, "plan_id": "T_PLAN_V1", "jurisdiction": "US",
    "scope": "US_FEDERAL",
    "source_roles": [{"role": "FEDERAL_REGISTER", "critical": True}],
    "source_endpoints": ["fr_documents_api"],
    "critical_sources": ["us_federal_register"],
    "query_taxonomy_version": "qt-v1",
    "query_set": {"fr_terms": ["a"], "fr_agencies": ["environmental-protection-agency"]},
    "language_set": ["en"],
    "time_window": {"from": "2024-01-01", "to": "2026-12-31"},
    "year_segments": [],
    "discovery_routes": ["A", "B"],
    "acceptance_rule_version": "1",
    "dedupe_rule_version": "v1",
}


def mk(**over) -> SearchPlan:
    return SearchPlan(**{**BASE, **over})


def test_hash_stable_and_hex():
    assert mk().plan_hash() == mk().plan_hash()
    assert len(mk().plan_hash()) == 64


def test_non_semantic_fields_excluded_from_hash():
    a = mk(created_at="2026-01-01", notes="x").plan_hash()
    b = mk(created_at="2026-09-13", notes="y").plan_hash()
    assert a == b


def test_every_semantic_field_changes_hash():
    base = mk().plan_hash()
    mutations = [
        {"plan_id": "T_PLAN_V2"},
        {"jurisdiction": "EU"},
        {"scope": "US_STATES"},
        {"source_roles": [{"role": "FEDERAL_REGISTER", "critical": False}]},
        {"source_endpoints": ["fr_single_doc_api"]},
        {"critical_sources": ["other_source"]},
        {"query_taxonomy_version": "qt-v2"},
        {"query_set": {"fr_terms": ["b"], "fr_agencies": ["environmental-protection-agency"]}},
        {"language_set": ["fr"]},
        {"time_window": {"from": "2023-01-01", "to": "2026-12-31"}},
        {"year_segments": ["32026R"]},
        {"discovery_routes": ["A"]},
        {"acceptance_rule_version": "2"},
        {"dedupe_rule_version": "v2"},
    ]
    for over in mutations:
        assert mk(**over).plan_hash() != base, f"字段变化未反映到 hash: {over}"


def test_real_plans_load_and_validate():
    for pid in ("US_FED_PLAN_V1", "EU_SUPRA_PLAN_V1"):
        plan = load_plan(pid)
        assert plan.plan_id == pid
        assert len(plan.plan_hash()) == 64
        assert validate_plan(plan) == []          # 无警告（critical_sources 已声明）


def test_registry_has_no_errors_and_contains_v1_plans():
    reg = build_registry()
    assert reg["errors"] == []
    ids = {p["plan_id"] for p in reg["plans"]}
    assert {"US_FED_PLAN_V1", "EU_SUPRA_PLAN_V1"} <= ids
    for p in reg["plans"]:
        assert len(p["plan_hash"]) == 64


def test_unknown_plan_fails_fast():
    with pytest.raises(ConfigError):
        load_plan("NO_SUCH_PLAN_V9")


def test_validate_rejects_unknown_endpoint():
    with pytest.raises(ConfigError):
        validate_plan(mk(source_endpoints=["nope_endpoint"]))


def test_validate_rejects_unknown_role():
    with pytest.raises(ConfigError):
        validate_plan(mk(source_roles=[{"role": "NOT_A_ROLE"}],
                         source_endpoints=[]))


def test_validate_rejects_version_drift():
    with pytest.raises(ConfigError):
        validate_plan(mk(acceptance_rule_version="99"))
    with pytest.raises(ConfigError):
        validate_plan(mk(dedupe_rule_version="v99"))


def test_validate_requires_search_material():
    with pytest.raises(ConfigError):
        validate_plan(mk(query_set={}, year_segments=[]))


def test_validate_rejects_bad_routes():
    with pytest.raises(ConfigError):
        validate_plan(mk(discovery_routes=["X"]))
