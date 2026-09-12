# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 10：scope 级饱和回归。

纪律：四个 scope 独立；US Federal 结果不得呈现为 "United States complete"；
州级/成员国角色不得混入 supra/federal 分母。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.scope_saturation import (  # noqa: E402
    SCOPES, SUB_NATIONAL_ROLES, _matrix_rows, scope_identity, scope_novelty,
    scope_routes, scope_universe,
)


def test_four_scopes_defined():
    assert SCOPES == ("EU_SUPRANATIONAL", "EU_MEMBER_STATES",
                      "US_FEDERAL", "US_STATES")


def test_us_federal_excludes_sub_national_roles():
    rows = _matrix_rows()
    assert rows, "需要先运行 scripts/audit_source_roles.py 生成矩阵"
    res = scope_universe("US_FEDERAL")
    expected_total = sum(1 for r in rows
                         if r["scope"] == "US_FEDERAL" and r.get("mandatory")
                         and r["source_role"] not in SUB_NATIONAL_ROLES)
    assert res["mandatory"]["total"] == expected_total
    # STATE_* 角色绝不出现在 US_FEDERAL 的 mandatory 口径中
    counted_roles = {r["source_role"] for r in rows
                     if r["scope"] == "US_FEDERAL" and r.get("mandatory")}
    assert not (counted_roles & SUB_NATIONAL_ROLES) or \
        res["mandatory"]["total"] < sum(1 for r in rows
                                        if r["scope"] == "US_FEDERAL")


def test_scope_universe_reflects_matrix_statuses():
    rows = _matrix_rows()
    for scope in ("EU_SUPRANATIONAL", "US_FEDERAL"):
        res = scope_universe(scope)
        assert res["available"] is True
        assert 0.0 <= res["mandatory_pct"] <= 100.0
        assert 0.0 <= res["critical_pct"] <= 100.0
        # 未覆盖角色必须给出状态（可解释）
        for o in res["open_roles"]:
            assert o["status"] in ("NOT_ONBOARDED", "DISCOVERED", "ACCESSIBLE",
                                   "PARTIAL", "BLOCKED")


def test_scope_novelty_shape():
    nov = scope_novelty("US_FEDERAL")
    assert set(nov) >= {"available", "novel_rate", "consecutive_rounds"}
    if nov["available"]:
        assert nov["metric"] == "accepted_novelty_rate"


def test_scope_identity_uses_overlay_for_us():
    from app.policy.backfill import load_records
    records = load_records(ROOT)
    if not records:
        return
    us = scope_identity(records, "US_FEDERAL")
    assert us["total"] > 0 and 0.0 <= us["pct"] <= 100.0


def test_scope_routes_shape():
    from app.policy.backfill import load_records
    records = load_records(ROOT)
    if not records:
        return
    r = scope_routes(records, "EU_SUPRANATIONAL")
    assert set(r["routes"]) == {"A_official_enumeration", "B_fulltext_native_language",
                                "C_legal_relation_expansion", "D_open_web_browser"}
    assert 0 <= r["count"] <= 4
