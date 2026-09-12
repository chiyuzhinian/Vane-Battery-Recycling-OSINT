# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 1：MODE A（扩张）/ MODE B（验证）分离。

纪律：MODE A 允许大发现但**不参与 SG8**；
只有 MODE B（convergence_validation）轮次可用于收敛 streak。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.rounds import convergence_status  # noqa: E402


def r(rid: str, rate: float, *, mode: str, validity: str = "FULL") -> dict:
    return {"round_id": rid, "accepted_novelty_rate": rate,
            "totals": {"source_failures": 0, "new_by_class": {}},
            "plan_hash": "H1", "round_mode": mode, "round_validity": validity}


def test_discovery_expansion_rounds_excluded():
    rounds = [r("v1", 0.01, mode="convergence_validation"),
              r("d1", 0.005, mode="discovery_expansion")]
    st = convergence_status(rounds, plan_hash="H1",
                            mode_required="convergence_validation")
    assert st["streak"] == 0 and st["converged"] is False


def test_legacy_mode_never_counts_in_validation():
    rounds = [r("a", 0.01, mode="legacy"), r("b", 0.005, mode="legacy")]
    st = convergence_status(rounds, plan_hash="H1",
                            mode_required="convergence_validation")
    assert st["streak"] == 0 and st["converged"] is False


def test_only_validation_rounds_count():
    rounds = [
        r("d1", 0.9, mode="discovery_expansion"),
        r("d2", 0.5, mode="discovery_expansion"),
        r("v1", 0.01, mode="convergence_validation"),
        r("v2", 0.005, mode="convergence_validation"),
    ]
    st = convergence_status(rounds, plan_hash="H1",
                            mode_required="convergence_validation")
    assert st["streak"] == 2 and st["converged"] is True
    assert st["mode_required"] == "convergence_validation"
