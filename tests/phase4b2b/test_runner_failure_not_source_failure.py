# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1R §Tests：runner 失败 ≠ source 失败（核心纪律）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.network_vantage import classify_access  # noqa: E402

MATRIX = ROOT / "outputs" / "audit" / "network_vantage_matrix.json"


def test_connection_failures_not_source_failure_single_vantage():
    """单 vantage 连接层失败 → CURRENT_RUNNER_BLOCKED（不得 SOURCE_FAILURE）。"""
    for tcp in ("timeout", "reset", "refused", "error"):
        r = classify_access(dns_status="ok", tcp_status=tcp,
                            tls_status="skipped")
        assert r["access_status"] == "CURRENT_RUNNER_BLOCKED", tcp
        assert r["awaiting_independent_runner"] is True
        assert r["access_status"] != "SOURCE_FAILURE"


def test_multi_vantage_blocked_requires_two_independent():
    r1 = classify_access(dns_status="ok", tcp_status="timeout",
                         independent_vantages_checked=1,
                         independent_vantages_failed=1)
    assert r1["access_status"] == "CURRENT_RUNNER_BLOCKED"
    r2 = classify_access(dns_status="ok", tcp_status="timeout",
                         independent_vantages_checked=2,
                         independent_vantages_failed=2)
    assert r2["access_status"] == "MULTI_VANTAGE_BLOCKED"


def test_matrix_never_escalates_without_evidence():
    """矩阵中 CURRENT_RUNNER_BLOCKED 行必须标注 awaiting（需独立复核）。"""
    if not MATRIX.exists():
        import pytest
        pytest.skip("需先运行 scripts/probe_network_vantage.py")
    d = json.loads(MATRIX.read_text(encoding="utf-8"))
    for row in d["rows"]:
        if row["access_status"] == "CURRENT_RUNNER_BLOCKED":
            assert row["awaiting_independent_runner"] is True, row["endpoint"]
