# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §2：SUPPORTING_REGULATION 归位（危废/危货 → 最高 B）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.domain_scope import (  # noqa: E402
    classify_domain_scope, guard_class, guarded_effective_class,
)


def _rec(eid="e", sid="us_ecfr", title="", text="", meta=None, **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_supporting_caps_a_to_b_only():
    assert guard_class("A1", "SUPPORTING_REGULATION") == "B"
    assert guard_class("A2", "SUPPORTING_REGULATION") == "B"
    assert guard_class("B", "SUPPORTING_REGULATION") == "B"
    assert guard_class("C", "SUPPORTING_REGULATION") == "C"
    assert guard_class("D", "SUPPORTING_REGULATION") == "D"


def test_hazmat_45cfr_is_supporting_b():
    r = _rec("c1", title="49 CFR Part 172 — Hazardous Materials Table, "
                         "Special Provisions",
             text="hazardous materials shipments packaging " * 20)
    assert classify_domain_scope(r) == "SUPPORTING_REGULATION"
    assert guarded_effective_class(r, "B") == "B"


def test_rcra_is_supporting_b():
    r = _rec("c2", title="Hazardous Waste Generator Improvements Rule",
             text="hazardous waste generators management " * 20)
    assert classify_domain_scope(r) == "SUPPORTING_REGULATION"
    assert guarded_effective_class(r, "B") == "B"


def test_e_manifest_and_ldr_are_supporting():
    for t in ("Integrating e-Manifest With Hazardous Waste Exports",
              "No-Migration Variance From Land Disposal Restrictions"):
        r = _rec("x", title=t)
        assert classify_domain_scope(r) == "SUPPORTING_REGULATION", t


def test_state_hazardous_waste_authorization_is_supporting():
    r = _rec("c3", title="Texas: Incorporation by Reference of State "
                         "Hazardous Waste Management Program")
    assert classify_domain_scope(r) == "SUPPORTING_REGULATION"


def test_core_title_still_wins_over_supporting():
    """标题级 CORE 优先于支撑体系词（traction battery + hazardous）→ CORE。"""
    r = _rec("c4", title="Vehicle traction battery packagers — "
                         "hazardous materials handling")
    assert classify_domain_scope(r) == "CORE_EV_TRACTION"
    assert guard_class("A1", "CORE_EV_TRACTION") == "A1"
