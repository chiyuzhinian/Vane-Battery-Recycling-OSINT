# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 8：metadata-first instrument 判定回归。

判定顺序：known_cases → FR type / CELEX 提案 → NIM 母语文种 → 结构化形状 →
corrigendum → 标题优先级 → CELEX 回退 → unknown。
纪律：AI 不得单独决定 binding force；不得用 URL 名称硬编码 case。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.instrument_audit import categorize  # noqa: E402
from app.policy.instruments import detect_instrument  # noqa: E402


def test_fr_type_metadata_first():
    r = detect_instrument("Some unrelated title", meta={"type": "Rule"})
    assert r.instrument_type == "administrative_rule" and r.binding_force == "binding"
    r2 = detect_instrument("Some unrelated title", meta={"type": "Proposed Rule"})
    assert r2.instrument_type == "proposal"


def test_celex_proposal_and_delegated_title_wins():
    r = detect_instrument("Proposal for a REGULATION ...",
                          meta={"celex": "52020PC0798"})
    assert r.instrument_type == "proposal"
    # 关键回归：CELEX 类型位 R 不得掩盖标题的 "Delegated Regulation"
    r2 = detect_instrument(
        "Commission Delegated Regulation (EU) 2025/606 of 21 March 2025",
        meta={"celex": "32025R0606"})
    assert r2.instrument_type == "delegated_act"
    r3 = detect_instrument(
        "Commission Implementing Regulation (EU) 2025/2289",
        meta={"celex": "32025R2289"})
    assert r3.instrument_type == "implementing_act"


def test_nim_native_doc_types():
    r = detect_instrument("Vyhláška č. 212/2015 Sb., kterou se mění vyhláška "
                          "č. 170/2012 Sb., o bateriích a akumulátorech")
    assert r.instrument_type == "administrative_rule" and r.binding_force == "binding"
    r2 = detect_instrument("Verordnung über die Bewirtschaftung von Abfällen")
    assert r2.instrument_type == "administrative_rule"


def test_guidance_before_regulation_priority():
    """标题提到 Regulation (EU) 2023/1542 的指引不得被判成 regulation。"""
    r = detect_instrument(
        "Commission Notice – Commission guidelines to facilitate the harmonised "
        "application of Regulation (EU) 2023/1542 concerning batteries")
    assert r.instrument_type == "official_guidance"


def test_structured_shapes():
    assert detect_instrument("40 CFR Part 273 — STANDARDS FOR UNIVERSAL WASTE "
                             "MANAGEMENT").instrument_type == "regulation"
    assert detect_instrument("U.S.C. Title 42 Chapter 82 — THE PUBLIC HEALTH "
                             "AND WELFARE").instrument_type == "statute"
    assert detect_instrument("Public Law 117-58 — An Act").instrument_type == "statute"
    assert detect_instrument("CBP Ruling N301234 — The tariff classification "
                             "of lithium-ion battery cells").instrument_type \
        == "official_guidance"


def test_celex_fallback_only_when_title_silent():
    r = detect_instrument("Смешанный заголовок без типа", meta={"celex": "32023R1542"})
    assert r.instrument_type == "regulation"       # 回退生效
    assert r.matched.startswith("meta:celex_fallback")


def test_mismatch_categorization():
    assert categorize({"source_id": "us_fr_1", "actual_instrument": "unknown",
                       "meta_keys": ["type"]}) == "SOURCE_METADATA_MISSING"
    assert categorize({"source_id": "eu_nim_cz", "actual_instrument": "unknown",
                       "title": "some long title"}) == "NIM_METADATA_INSUFFICIENT"
    assert categorize({"source_id": "x", "actual_instrument": "regulation",
                       "title": "Whatever"}) == "RULE_MAPPING_ERROR"
    assert categorize({"source_id": "x", "actual_instrument": "unknown",
                       "title": "12"}) == "TITLE_INSUFFICIENT"
    assert categorize({"source_id": "x", "actual_instrument": "unknown",
                       "title": "A reasonably long title here"}) \
        == "UNKNOWN_DOCUMENT_CLASS"
