# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 4：Domain Scope Guard 测试（分类 / 约束矩阵 / 豁免）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.domain_scope import (  # noqa: E402
    NON_POLICY_PREFIXES, classify_domain_scope, guard_class,
    guarded_effective_class, is_policy_domain_source,
)


def _rec(sid="eu_eurlex_battery_reg", title="", text="", **kw):
    r = {"evidence_id": "e1", "source_id": sid, "title": title, "text": text,
         "meta": {}}
    r.update(kw)
    return r


def test_core_ev_traction_title_level():
    r = _rec(title="Regulation on end-of-life electric vehicle batteries")
    assert classify_domain_scope(r) == "CORE_EV_TRACTION"
    assert classify_domain_scope(_rec(title="Black mass recovery rules")) \
        == "CORE_EV_TRACTION"


def test_horizontal_system_acts():
    r = _rec(title="Regulation (EU) 2023/1542 concerning batteries")
    assert classify_domain_scope(r) == "HORIZONTAL_APPLIES_TO_EV"
    r2 = _rec(title="Waste shipments regulation update")
    assert classify_domain_scope(r2) == "HORIZONTAL_APPLIES_TO_EV"


def test_general_battery_background():
    r = _rec(title="Arrêté fixant les conditions de collecte des "
                   "piles et accumulateurs portables")
    assert classify_domain_scope(r) == "GENERAL_BATTERY_BACKGROUND"
    r2 = _rec(title="Li-ion batteries in e-bike applications")
    assert classify_domain_scope(r2) == "GENERAL_BATTERY_BACKGROUND"


def test_guard_class_matrix():
    # GENERAL：A1/A2/B → C（核心防护）
    assert guard_class("A2", "GENERAL_BATTERY_BACKGROUND") == "C"
    assert guard_class("B", "GENERAL_BATTERY_BACKGROUND") == "C"
    assert guard_class("D", "GENERAL_BATTERY_BACKGROUND") == "D"
    # OUT_OF_SCOPE：仅降 A1/A2（B 保留——eCFR 实测判例）
    assert guard_class("A2", "OUT_OF_SCOPE") == "D"
    assert guard_class("B", "OUT_OF_SCOPE") == "B"
    # SUPPORTING：A1/A2 → B
    assert guard_class("A1", "SUPPORTING_REGULATION") == "B"
    assert guard_class("B", "SUPPORTING_REGULATION") == "B"
    # CORE/HORIZONTAL 无约束
    assert guard_class("A1", "CORE_EV_TRACTION") == "A1"
    assert guard_class("A2", "HORIZONTAL_APPLIES_TO_EV") == "A2"


def test_non_policy_sources_exempt():
    for p in NON_POLICY_PREFIXES:
        assert not is_policy_domain_source(f"{p}_some_id")
    assert is_policy_domain_source("eu_nim_se")
    assert is_policy_domain_source("us_ecfr_40_260")
    # 企业线记录不被护栏改写
    r = _rec(sid="cninfo", title="Battery recycling investment announcement",
            text="battery recycling " * 50)
    assert guarded_effective_class(r, "B") == "B"


def test_nim_out_of_scope_exempt_but_general_guarded():
    # NIM + 多语言域外误判 → 豁免（保持原类）
    r = _rec(sid="eu_nim_be", title="Arrêté relatif à l'immatriculation")
    assert guarded_effective_class(r, "A2") == "A2"
    # NIM + 泛电池背景 → 仍受 GENERAL 防护
    r2 = _rec(sid="eu_nim_fi",
             title="Valtioneuvoston asetus paristoista ja akuista")
    assert classify_domain_scope(r2) == "GENERAL_BATTERY_BACKGROUND"
    assert guarded_effective_class(r2, "A2") == "C"
