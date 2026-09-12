# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 1：Search Plan 变更 → convergence RESET。

纪律：plan_hash 不一致的轮次不得组成同一 streak；
搜索空间变化必须表现为"新 plan 从头计数"。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.rounds import convergence_status  # noqa: E402


def r(rid: str, rate: float, *, ph: str = "", mode: str = "convergence_validation",
      validity: str = "FULL") -> dict:
    return {"round_id": rid, "accepted_novelty_rate": rate,
            "totals": {"source_failures": 0, "new_by_class": {}},
            "plan_hash": ph, "round_mode": mode, "round_validity": validity}


def test_same_plan_two_low_rounds_converge():
    rounds = [r("a", 0.5, ph="H1"), r("b", 0.01, ph="H1"), r("c", 0.005, ph="H1")]
    st = convergence_status(rounds, plan_hash="H1",
                            mode_required="convergence_validation")
    assert st["converged"] is True and st["streak"] == 2
    assert st["plan_bound"] is True


def test_plan_change_resets_streak():
    """H1 已有低novelty轮，换 H2 后不得与旧轮拼接。"""
    rounds = [r("a", 0.01, ph="H1"), r("b", 0.005, ph="H2")]
    st = convergence_status(rounds, plan_hash="H2",
                            mode_required="convergence_validation")
    assert st["streak"] == 1 and st["converged"] is False


def test_mixed_hash_cannot_join():
    rounds = [r("a", 0.01, ph="H1"), r("b", 0.005, ph="H2")]
    st = convergence_status(rounds, plan_hash="H1",
                            mode_required="convergence_validation")
    assert st["streak"] == 0 and st["converged"] is False


def test_plan_changes_are_visible_in_output():
    rounds = [r("a", 0.01, ph="H1"), r("b", 0.005, ph="H2")]
    st = convergence_status(rounds)
    assert len(st["plan_changes"]) == 1
    change = st["plan_changes"][0]
    assert change["round_id"] == "b"
    assert change["from"] == "H1" and change["to"] == "H2"


def test_legacy_rounds_not_eligible_under_strict_plan():
    rounds = [r("a", 0.01), r("b", 0.005)]          # 无 plan_hash（4B-1 历史）
    st = convergence_status(rounds, plan_hash="H1",
                            mode_required="convergence_validation")
    assert st["streak"] == 0 and st["converged"] is False
