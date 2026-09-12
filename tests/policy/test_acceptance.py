# -*- coding: utf-8 -*-
"""验收分类回归（Phase 4A §16 风险 5–10）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.acceptance import classify_record  # noqa: E402


def _rec(**kw) -> dict:
    base = {"evidence_id": "t1", "title": "", "text": "", "meta": {},
            "relevant": True, "rejected_by": None, "source_id": "x",
            "channel": "connector", "review_reason": None}
    base.update(kw)
    return base


def test_a2_battery_regulation_fixture():
    r = _rec(title="Regulation (EU) 2023/1542 concerning batteries and waste batteries",
             text="waste batteries recycling collection targets",
             meta={"celex": "32023R1542"})
    assert classify_record(r).classification == "A2"


def test_a2_placeholder_title_via_core_celex():
    """占位标题的记录也能认体系成员（数据质量兼容）。"""
    r = _rec(title="EU legislation CELEX 32023R1542", meta={"celex": "32023R1542"})
    assert classify_record(r).classification == "A2"


def test_b_transport_rule_clause_evidence():
    r = _rec(title="Hazardous Materials: Enhanced Safety Provisions for Lithium Batteries Transported by Aircraft",
             text="This rule revises requirements for the transport of lithium batteries. "
                  "Damaged cells must be shipped per 49 CFR 173.185.",
             meta={"document_number": "2019-03812"})
    res = classify_record(r)
    assert res.classification == "B"
    assert res.evidence_quotes, "B 类必须有条款证据"


def test_d_information_page_rejected():
    r = _rec(title="Understanding the Risks of DDR Lithium Batteries",
             rejected_by="info_page:Understanding")
    assert classify_record(r).classification == "D"


def test_d_off_scope_object():
    r = _rec(title="Used Household Batteries | US EPA",
             text="household battery management")
    assert classify_record(r).classification == "D"


def test_c_theme_only_no_clause():
    """泛主题（财税/战略）无回收条款证据 → C 背景，不得进 A/B 主库。"""
    r = _rec(title="Notice of Final Determination on 2025 DOE Critical Materials List",
             text="The list identifies critical minerals and materials.")
    assert classify_record(r).classification in ("C", "D")


def test_black_mass_title_without_literal_word_is_b():
    """法规标题没有 black mass 字面词，但条款级约束运输 → B（风险 9）。"""
    r = _rec(title="Regulation (EU) 2024/1157 on shipments of waste",
             text="Shipments of waste batteries and intermediate wastes derived from battery recycling "
                  "are subject to prior written notification and consent procedures.",
             meta={"celex": "32024R1157"})
    assert classify_record(r).classification == "A2"  # 体系锚点优先（WSR 族）


def test_native_language_not_killed():
    """母语文档不因没有英文标题被误杀（风险 10）。"""
    r = _rec(title="Vyhláška o bateriích a akumulátorech",
             source_id="eu_nim_cz", meta={"nim_id": "283350"})
    res = classify_record(r)
    assert res.classification == "A2"
    assert res.relevant
