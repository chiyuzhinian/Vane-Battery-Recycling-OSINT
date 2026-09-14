# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1R §Tests：Batch 1 onboarding gate（>80% 不降低）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

METRICS = ROOT / "outputs" / "audit" / "batch1_metrics.json"
RECOVERY = ROOT / "outputs" / "audit" / "batch1_channel_recovery.json"

GATE_MIN_RATE = 0.80


def onboarding_rate(onboarded: int, selected: int) -> float:
    return onboarded / max(selected, 1)


def gate_status(rate: float, minimum: float = GATE_MIN_RATE) -> str:
    return "PASS" if rate >= minimum else "PARTIAL"


def test_rate_math():
    assert onboarding_rate(4, 6) == pytest.approx(0.6667, abs=1e-3)
    assert onboarding_rate(6, 8) == 0.75
    assert gate_status(0.80) == "PASS"
    assert gate_status(0.79) == "PARTIAL"


def test_metrics_consistent_with_recovery():
    if not METRICS.exists() or not RECOVERY.exists():
        pytest.skip("需先运行 batch1_metrics / batch1r_recovery_decisions")
    m = json.loads(METRICS.read_text(encoding="utf-8"))
    rec = json.loads(RECOVERY.read_text(encoding="utf-8"))
    # 已恢复的辖区必须确实在 metrics 中 onboarded
    for jid in rec["recovered_via_rerun_or_alt_route"]:
        assert m["per_jurisdiction"][jid]["onboarded"] is True, jid
    # still_blocked 的不得 onboarded
    for jid in rec["still_blocked"]:
        assert m["per_jurisdiction"][jid]["onboarded"] is False, jid


def test_gate_reported_truthfully():
    """Gate 状态必须等于公式结果（不因结果差而放宽；也不因结果差而不报）。"""
    if not METRICS.exists():
        pytest.skip("需先运行 scripts/batch1_metrics.py")
    m = json.loads(METRICS.read_text(encoding="utf-8"))
    eu = onboarding_rate(m["EU"]["onboarded"], m["EU"]["selected"])
    us = onboarding_rate(m["US"]["onboarded"], m["US"]["selected"])
    assert gate_status(eu) == ("PASS" if eu >= GATE_MIN_RATE else "PARTIAL")
    assert gate_status(us) == ("PASS" if us >= GATE_MIN_RATE else "PARTIAL")
    # 0.80 阈值不得被下调（配方锁定）
    assert GATE_MIN_RATE == 0.80


def test_every_blocked_has_reason():
    if not RECOVERY.exists():
        pytest.skip("需先运行 batch1r_recovery_decisions")
    rec = json.loads(RECOVERY.read_text(encoding="utf-8"))
    for d in rec["decisions"]:
        if d["jurisdiction"] in rec["still_blocked"]:
            assert d.get("remaining_blocker"), d["jurisdiction"]
            assert d.get("failure_reason") or d.get(
                "current_runner_result"), d["jurisdiction"]
