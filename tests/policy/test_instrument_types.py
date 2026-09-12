# -*- coding: utf-8 -*-
"""文书类型 & 约束力回归（Phase 4A 风险 6–7）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.instruments import detect_instrument  # noqa: E402


def test_phmsa_advisory_is_non_binding():
    r = detect_instrument(
        "Safety Advisory Notice for the Transportation of Lithium Batteries "
        "for Disposal or Recycling")
    assert r.instrument_type == "advisory"
    assert r.binding_force == "non_binding"
    assert r.is_known_case


def test_proposal_not_effective():
    r = detect_instrument("Proposal for a REGULATION OF THE EUROPEAN PARLIAMENT "
                          "concerning batteries and waste batteries")
    assert r.instrument_type == "proposal"
    assert r.binding_force == "proposal"


def test_delegated_and_implementing():
    assert detect_instrument(
        "Commission Delegated Regulation (EU) 2025/606 supplementing ..."
    ).instrument_type == "delegated_act"
    assert detect_instrument(
        "Commission Implementing Regulation (EU) 2025/2289 laying down rules ..."
    ).instrument_type == "implementing_act"


def test_corrigendum_inherits_type():
    r = detect_instrument(
        "Corrigendum to Commission Delegated Regulation (EU) 2025/606 of 21 March 2025")
    assert r.instrument_type == "delegated_act"


def test_information_page_detected():
    assert detect_instrument(
        "Understanding the Risks of Damaged, Defective, or Recalled (DDR) "
        "Lithium Batteries").instrument_type == "information_page"


def test_guidance_not_binding():
    r = detect_instrument("Commission Notice – Commission guidelines to "
                          "facilitate the harmonised application ...")
    assert r.instrument_type == "official_guidance"
    assert r.binding_force == "non_binding"


def test_final_rule_is_binding():
    # 用真实完整标题（判例锚点匹配 —— 与 goldset 案例一致）
    r = detect_instrument(
        "Hazardous Materials: Enhanced Safety Provisions for Lithium Batteries "
        "Transported by Aircraft (FAA Reauthorization Act of 2018)")
    assert r.instrument_type == "administrative_rule"
    assert r.binding_force == "binding"
    assert r.is_known_case


def test_fr_final_rule_phrase():
    r = detect_instrument(
        "Some Agency: Final Rule on Hazardous Waste Permits")
    assert r.instrument_type == "administrative_rule"
    assert r.binding_force == "binding"
