# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 10：SG8 收敛判据回归（accepted_novelty_rate 主判据）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.rounds import (  # noqa: E402
    CONVERGENCE_ROUNDS, NOVEL_RATE_THRESHOLD, convergence_status,
)


def _r(rate: float, failures: int = 0, rid: str = "R") -> dict:
    return {"round_id": rid, "accepted_novelty_rate": rate,
            "totals": {"source_failures": failures}}


def test_thresholds_documented():
    assert NOVEL_RATE_THRESHOLD == 0.02
    assert CONVERGENCE_ROUNDS == 2


def test_no_convergence_with_single_low_round():
    st = convergence_status([_r(0.5), _r(0.01)])
    assert st["converged"] is False and st["streak"] == 1


def test_two_consecutive_low_rounds_converge():
    st = convergence_status([_r(0.5), _r(0.015), _r(0.005)])
    assert st["converged"] is True and st["streak"] == 2


def test_failure_round_blocks_convergence_evidence():
    """含 source failure 的轮次不得作为收敛证据（且中断计数）。"""
    st = convergence_status([_r(0.01), _r(0.001, failures=2), _r(0.005)])
    assert st["converged"] is False
    assert st["streak"] == 1


def test_novelty_not_diluted_by_raw_noise():
    """宽泛检索：raw 噪声高但 novelty 高 → 不得判收敛（用户示例）。"""
    # 5 新入选 + 5 重复入选 → 0.5，即便 raw_yield 很低
    st = convergence_status([{"round_id": "noisy", "accepted_novelty_rate": 0.5,
                              "totals": {"source_failures": 0}}])
    assert st["converged"] is False
