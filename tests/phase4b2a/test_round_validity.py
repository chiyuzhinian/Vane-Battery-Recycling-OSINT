# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 1：Round Validity（FULL / PARTIAL / INVALID）语义。

纪律（用户规格 §六）：
    · INVALID = critical 源失败且零成功（本轮未完成）→ 不得计入 streak
    · PARTIAL = 其他失败 → 不计入 streak（保守口径）且中断扫描
    · 瞬态重试恢复 → FULL（仅记 transient_failures）——网络故障 ≠ 无结果
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.rounds import (  # noqa: E402
    build_round_record, convergence_status, derive_validity,
)


def _route(new: int = 0, dup: int = 0, failures: int = 0) -> dict:
    denom = new + dup
    return {"id": "A", "name": "official_enumeration", "queries": [],
            "raw_found": denom + 10, "unique_candidate_count": denom,
            "accepted_count": denom, "new_unique_accepted_count": new,
            "duplicate_accepted_count": dup, "rejected_count": 0,
            "new_documents_total": new, "accepted_by_class": {},
            "new_by_class": {}, "new_high_risk_B": 0,
            "source_failures": [{"source": "x", "failure": "ConnectError"}]
            * failures,
            "raw_yield": 0.0,
            "accepted_novelty_rate": (new / denom) if denom else 0.0}


def test_derive_validity_rules():
    assert derive_validity(failures=0, critical_failed_no_success=False) == "FULL"
    assert derive_validity(failures=1, critical_failed_no_success=False) == "PARTIAL"
    assert derive_validity(failures=1, critical_failed_no_success=True) == "INVALID"
    assert derive_validity(failures=0, critical_failed_no_success=True) == "INVALID"


def test_record_validity_defaults_and_override():
    rec_ok = build_round_record(round_id="t", scope="US_FEDERAL", started_at="a",
                                ended_at="b", routes=[_route()])
    assert rec_ok["round_validity"] == "FULL"
    rec_deg = build_round_record(round_id="t", scope="US_FEDERAL", started_at="a",
                                 ended_at="b", routes=[_route(failures=1)])
    assert rec_deg["round_validity"] == "PARTIAL"
    rec_inv = build_round_record(round_id="t", scope="US_FEDERAL", started_at="a",
                                 ended_at="b", routes=[_route(failures=1)],
                                 validity="INVALID")
    assert rec_inv["round_validity"] == "INVALID"
    assert rec_inv["schema_version"] == "phase4b2a.v1"


def test_transient_failures_recorded():
    rec = build_round_record(round_id="t", scope="US_FEDERAL", started_at="a",
                             ended_at="b", routes=[_route(new=1, dup=1)],
                             transient_failures=2)
    assert rec["totals"]["transient_failures"] == 2


def test_partial_round_breaks_scan_and_not_counted():
    rounds = [
        {"round_id": "a", "accepted_novelty_rate": 0.01,
         "totals": {"source_failures": 0}, "round_validity": "FULL"},
        {"round_id": "b", "accepted_novelty_rate": 0.005,
         "totals": {"source_failures": 1}, "round_validity": "PARTIAL"},
        {"round_id": "c", "accepted_novelty_rate": 0.01,
         "totals": {"source_failures": 0}, "round_validity": "FULL"},
    ]
    st = convergence_status(rounds)
    assert st["streak"] == 1                 # 只有 c 可计数；b 中断扫描
    assert st["converged"] is False


def test_invalid_round_breaks_scan():
    rounds = [
        {"round_id": "a", "accepted_novelty_rate": 0.005,
         "totals": {"source_failures": 0}, "round_validity": "FULL"},
        {"round_id": "b", "accepted_novelty_rate": 0.001,
         "totals": {"source_failures": 2}, "round_validity": "INVALID"},
        {"round_id": "c", "accepted_novelty_rate": 0.005,
         "totals": {"source_failures": 0}, "round_validity": "FULL"},
    ]
    st = convergence_status(rounds)
    assert st["streak"] == 1 and st["converged"] is False


def test_legacy_dict_without_validity_keeps_old_semantics():
    """向后兼容：4B-1 风格轮次（无 validity 字段）→ 失败轮 break。"""
    rounds = [
        {"round_id": "a", "accepted_novelty_rate": 0.01,
         "totals": {"source_failures": 0}},
        {"round_id": "b", "accepted_novelty_rate": 0.001,
         "totals": {"source_failures": 2}},
        {"round_id": "c", "accepted_novelty_rate": 0.005,
         "totals": {"source_failures": 0}},
    ]
    st = convergence_status(rounds)
    assert st["streak"] == 1 and st["converged"] is False
