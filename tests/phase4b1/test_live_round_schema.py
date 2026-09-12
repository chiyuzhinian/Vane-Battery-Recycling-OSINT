# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 10：LIVE 轮次 schema 与指标回归。

纪律（用户修正 2026-09-12）：
    · accepted_novelty_rate = 新入选/(新入选+重复入选) ← SG8 主判据
    · raw_yield = 新入选/raw ← 仅检索效率，不得单独证明饱和
    · source failure ≠ 0 结果；失败轮不得作为收敛证据
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.rounds import (  # noqa: E402
    ACCEPTED_CLASSES, RouteResult, accepted_novelty_rate, build_round_record,
    raw_yield,
)

REQUIRED_ROUTE_FIELDS = (
    "id", "name", "queries", "raw_found", "unique_candidate_count",
    "accepted_count", "new_unique_accepted_count", "duplicate_accepted_count",
    "rejected_count", "source_failures", "raw_yield", "accepted_novelty_rate",
)


def _route() -> RouteResult:
    rr = RouteResult("B", "native_fulltext_search", queries=["q1"])
    rr.raw_found = 100
    return rr


def test_round_schema_complete():
    rr = _route()
    rr.candidates = [
        {"evidence_id": "new-1"},      # 新 + B → accepted
        {"evidence_id": "new-2"},      # 新 + D → rejected
        {"evidence_id": "dup-1"},      # 既有 + A2 → duplicate accepted
    ]
    classified = {"new-1": "B", "new-2": "D", "dup-1": "A2"}
    d = rr.as_dict(classified=classified, existing_ids={"dup-1"})
    for f in REQUIRED_ROUTE_FIELDS:
        assert f in d, f
    assert d["new_unique_accepted_count"] == 1
    assert d["duplicate_accepted_count"] == 1
    assert d["rejected_count"] == 1
    assert d["accepted_count"] == 2
    assert d["raw_yield"] == raw_yield(1, 100)


def test_source_failure_not_zero_result():
    rr = _route()
    rr.source_failures = [{"source": "x", "failure": "HTTP_403"}]
    d = rr.as_dict(classified={}, existing_ids=set())
    assert d["source_failures"] and d["raw_found"] == 100       # 失败与 0 结果分开
    record = build_round_record(round_id="t", scope="US_FEDERAL",
                                started_at="a", ended_at="b", routes=[d])
    assert record["totals"]["source_failures"] == 1


def test_novelty_and_yield_formulas():
    assert accepted_novelty_rate(1, 1) == 0.5
    assert accepted_novelty_rate(0, 0) == 0.0
    assert raw_yield(5, 1000) == 0.005
    # ★ raw_yield 可被噪声稀释 → 不得作饱和证据（文档与 SG8 使用 novelty）
    assert raw_yield(5, 1000) < 0.02
    assert accepted_novelty_rate(5, 5) == 0.5                    # 实际远未饱和


def test_accepted_definition_excludes_d_only():
    assert set(ACCEPTED_CLASSES) == {"A1", "A2", "B", "C"}
    assert "D" not in ACCEPTED_CLASSES
