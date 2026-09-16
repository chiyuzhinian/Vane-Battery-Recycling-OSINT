# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1C：验收表构建器单元测试（无网络）。

覆盖：
  · 记录级五态机（§八：禁止 relevant=true 终态）
  · Gate（§十二）：高价值文书门槛 / 空类 vacuous 口径
  · 中文业务字段受控词表生成（§十）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_acceptance_table as bat  # noqa: E402


def _rec(**kw):
    base = {"evidence_id": "x_1", "source_id": "cz_psp", "region": "EU",
            "url": "https://example.gov/x", "title": "170/2010 Sb.",
            "meta": {"jurisdiction": "CZ", "doc_key": "CZ:SB:170/2010",
                     "language": "cs",
                     "source_role": "MS_LEGISLATION_DATABASE"},
            "text": "x" * 2000}
    base.update(kw)
    return base


def test_review_status_five_state_machine():
    assert bat.status_of("D", {}, None, "")[0] == "EXCLUDED"
    assert bat.status_of("C", {}, None, "")[0] == "BACKGROUND"
    # B 无条款证据 → B_CANDIDATE / REVIEW_REQUIRED（不得 confirmed B，§九）
    st, notes = bat.status_of("B", _rec(), None, "")
    assert st == "REVIEW_REQUIRED"
    assert "B_CANDIDATE_NO_CLAUSE" in notes


def test_gate_requires_high_value_docs():
    gate = bat.gate_of("US-MI", "state", [], [], {"roles": []},
                       {"state": "NOT_YET_CONVERGED"},
                       {"p0_missing": []},
                       bat.evidence_summary_of([]), 0)
    assert gate["JURISDICTION_CORPUS_ACCEPTED"] is False
    assert gate["checks"]["high_value_docs_ge_1"] is False


def test_evidence_summary_vacuous_classes_full_credit():
    ev = bat.evidence_summary_of([])
    for cls in ("A1", "A2", "B"):
        assert ev[cls]["n"] == 0
        assert ev[cls]["fulltext_pct"] == 100.0
        assert ev[cls]["clause_pct"] == 100.0


def test_biz_fields_are_controlled_vocab_based():
    from app.policy.config import load_topics
    cfg = load_topics()
    row = {"country_or_state": "捷克", "instrument_type": "regulation",
           "title": "170/2010 Sb.", "official_identifier": "170/2010",
           "topic_ids": ["T02"], "legal_status": "unknown"}
    bf = bat.biz_fields(row, cfg)
    assert bf["affected_actor"]                       # 受控映射非空
    assert bf["effective_status_cn"] == "待人工核验"
    assert "回收" in bf["compliance_obligation_cn"]\
        or "收集" in bf["compliance_obligation_cn"]


def test_scope_constants_cover_batch1():
    assert bat.BATCH1_EU == ["AT", "HU", "CZ", "SK", "IT"]
    assert set(bat.BATCH1_US) == {"US-MI", "US-GA", "US-IL", "US-TN",
                                  "US-TX", "US-NV", "US-CO"}
    assert "BE" in bat.BLOCKED_WITH_EVIDENCE
    assert "US-OH" in bat.BLOCKED_WITH_EVIDENCE
