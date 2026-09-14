# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1R §Tests：network vantage 分类。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.network_vantage import ACCESS_STATUSES, classify_access  # noqa: E402


def test_http_200_is_source_available():
    r = classify_access(dns_status="ok", tcp_status="ok", tls_status="ok",
                        http_status=200, content_len=50000)
    assert r["access_status"] == "SOURCE_AVAILABLE"
    assert r["source_vs_runner"] == "SOURCE"


def test_js_shell_is_partial():
    r = classify_access(dns_status="ok", tcp_status="ok", tls_status="ok",
                        http_status=200, content_len=3000, js_rendered=True)
    assert r["access_status"] == "SOURCE_PARTIAL"
    assert r["failure_reason"] == "JS_RENDERED_NO_STATIC_CONTENT"


def test_403_is_access_controlled():
    r = classify_access(dns_status="ok", tcp_status="ok", tls_status="ok",
                        http_status=403, content_len=900)
    assert r["access_status"] == "ACCESS_CONTROLLED"


def test_503_challenge_is_access_controlled():
    r = classify_access(dns_status="ok", tcp_status="ok", tls_status="ok",
                        http_status=503, content_len=30618)
    assert r["access_status"] == "ACCESS_CONTROLLED"


def test_nxdomain_with_doh_confirmation_is_source_failure():
    r = classify_access(dns_status="nxdomain", doh_confirms="nxdomain")
    assert r["access_status"] == "SOURCE_FAILURE"
    r2 = classify_access(dns_status="nxdomain", doh_confirms="ok")
    assert r2["access_status"] == "UNKNOWN"   # 未确认不得判源失败


def test_alt_vantage_ok_marks_runner_blocked():
    r = classify_access(dns_status="ok", tcp_status="timeout",
                        alt_vantage_ok=True)
    assert r["access_status"] == "CURRENT_RUNNER_BLOCKED"
    assert r["failure_reason"] == "ALT_VANTAGE_OK"
    assert r["source_vs_runner"] == "RUNNER"


def test_official_alt_route_ok_marks_runner_blocked():
    r = classify_access(dns_status="ok", http_status=503, content_len=100,
                        official_alt_used=True)
    assert r["access_status"] == "CURRENT_RUNNER_BLOCKED"
    assert r["failure_reason"] == "OFFICIAL_ALT_ROUTE_OK"


def test_all_statuses_are_declared():
    r = classify_access()
    assert r["access_status"] in ACCESS_STATUSES
