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


def test_nim_discovery_layer_capped_c():
    """2B1：NIM 不得 force A1/A2/B——多语言 NIM 记录封顶 C（discovery 层）。

    原测试（4A）期望 NIM 母语文档自动 A2；2B1 起 NIM 只是发现索引，
    national 实施须由各国官方通道采集（见 test_nim_discovery_only.py）。
    """
    r = _rec(title="Vyhláška o bateriích a akumulátorech",
             source_id="eu_nim_cz", meta={"nim_id": "283350"})
    res = classify_record(r)
    assert res.classification == "C"
    assert res.relevant is False
    assert "C_DISCOVERY_LAYER_NIM" in res.reason_codes


def test_reclassify_acceptance_output_record_not_trapped():
    """Batch 1C（2026-09-16）：本系统产出记录（meta.acceptance_class 存在）
    的 relevant 是验收标志位（C/D → False），重分类不得早退 D。"""
    r = _rec(title="170/2010 Sb. Vyhláška o bateriích a akumulátorech",
             text="sběr přenosných baterií a akumulátorů",
             relevant=False,
             meta={"acceptance_class": "C", "jurisdiction": "CZ"})
    res = classify_record(r)
    assert res.classification in ("B", "C"), res.reason_codes


def test_legacy_rejection_without_acceptance_class_still_d():
    """旧判定器拒绝（无 acceptance_class 标记）→ 维持 D（拒绝优先）。"""
    r = _rec(title="Some page", text="no relevant content",
             relevant=False, meta={})
    assert classify_record(r).classification == "D"


def test_relevant_none_falls_through_to_content():
    """relevant=None（字段存在但空）→ 走内容分类，不再早退。"""
    r = _rec(title="Waste battery management",
             text="waste battery collection and recycling obligations",
             relevant=None, meta={})
    assert classify_record(r).classification in ("B", "C")
