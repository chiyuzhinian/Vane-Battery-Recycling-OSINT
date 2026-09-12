# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 1：class 级新颖度（new_A1..D / new_high_risk_B）+ 高价值护栏。

纪律（用户规格 §五）：
    即使 overall novelty 很低，只要仍不断出现新的 A1 / high-risk B（或每轮仍在
    新增 A2 核心政策语料），**不得轻易宣布 SATURATED**。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.rounds import (  # noqa: E402
    HIGH_RISK_B_TOPICS, RouteResult, build_round_record, convergence_status,
)


def test_route_new_by_class_and_high_risk_b():
    rr = RouteResult("B", "native_fulltext_search")
    rr.raw_found = 30
    rr.candidates = [
        {"evidence_id": "n1"}, {"evidence_id": "n2"},
        {"evidence_id": "n3"}, {"evidence_id": "d1"},
    ]
    classified = {"n1": "A2", "n2": "B", "n3": "C", "d1": "A2"}
    topics = {"n2": ["T05"], "n1": ["T14"]}
    d = rr.as_dict(classified=classified, existing_ids={"d1"},
                   topics_by_id=topics)
    assert d["new_by_class"] == {"A2": 1, "B": 1, "C": 1}
    assert d["new_high_risk_B"] == 1
    assert HIGH_RISK_B_TOPICS == ("T01", "T02", "T05", "T10", "T13")


def test_high_risk_b_requires_both_class_and_topic():
    rr = RouteResult("B", "b")
    rr.candidates = [{"evidence_id": "n1"}, {"evidence_id": "n2"}]
    classified = {"n1": "B", "n2": "A2"}
    topics = {"n1": ["T14"], "n2": ["T05"]}      # T14 非高风险；A2 不算
    d = rr.as_dict(classified=classified, existing_ids=set(),
                   topics_by_id=topics)
    assert d["new_high_risk_B"] == 0


def test_build_round_record_aggregates_classes():
    ra = RouteResult("A", "a")
    ra.candidates = [{"evidence_id": "x1"}, {"evidence_id": "x2"}]
    rb = RouteResult("B", "b")
    rb.candidates = [{"evidence_id": "y1"}]
    classified = {"x1": "A2", "x2": "B", "y1": "A1"}
    topics = {"x2": ["T10"], "y1": []}
    routes = [ra.as_dict(classified=classified, existing_ids=set(),
                         topics_by_id=topics),
              rb.as_dict(classified=classified, existing_ids=set(),
                         topics_by_id=topics)]
    rec = build_round_record(round_id="t", scope="US_FEDERAL", started_at="a",
                             ended_at="b", routes=routes)
    tot = rec["totals"]
    assert tot["new_by_class"] == {"A2": 1, "B": 1, "A1": 1}
    assert tot["new_high_risk_B"] == 1


def _low(rid: str, classes: dict | None = None, hb: int = 0) -> dict:
    return {"round_id": rid, "accepted_novelty_rate": 0.005,
            "totals": {"source_failures": 0,
                       "new_by_class": classes or {},
                       "new_high_risk_B": hb}}


def test_new_a1_blocks_saturation():
    rounds = [_low("a", {"A2": 5}), _low("b", {"A1": 1})]
    st = convergence_status(rounds)
    assert st["streak"] == 2                    # 数值上达标
    assert st["converged"] is False             # 但被高价值护栏阻断
    assert st["blocked_by_high_value"] is True
    assert "A1" in st["blocked_reason"]


def test_new_high_risk_b_blocks_saturation():
    rounds = [_low("a", {"B": 3}), _low("b", {"B": 2}, hb=1)]
    st = convergence_status(rounds)
    assert st["converged"] is False
    assert st["blocked_by_high_value"] is True
    assert "high_risk_B" in st["blocked_reason"]


def test_sustained_a2_blocks_saturation():
    rounds = [_low("a", {"A2": 2}), _low("b", {"A2": 3})]
    st = convergence_status(rounds)
    assert st["converged"] is False
    assert "new_A2" in st["blocked_reason"]


def test_clean_low_rounds_converge_without_block():
    rounds = [_low("a", {"C": 1}), _low("b", {})]
    st = convergence_status(rounds)
    assert st["streak"] == 2 and st["converged"] is True
    assert st["blocked_by_high_value"] is False


def test_legacy_rounds_without_class_data_not_blocked():
    """兼容：无 new_by_class 字段的历史轮次不得被误判为 sustained A2。"""
    rounds = [
        {"round_id": "a", "accepted_novelty_rate": 0.015,
         "totals": {"source_failures": 0}},
        {"round_id": "b", "accepted_novelty_rate": 0.005,
         "totals": {"source_failures": 0}},
    ]
    st = convergence_status(rounds)
    assert st["converged"] is True and st["blocked_by_high_value"] is False
