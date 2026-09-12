# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 6：OECD 文书类型 + SPA 端点回归。

纪律：
    · OECD Decision → binding（对成员有约束力）；Recommendation → non_binding
    · SPA（JS 渲染）端点：可达但不可抽取 → PARTIAL，且**不得**当作可用端点
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.crossborder import oecd_instrument  # noqa: E402
from app.policy.source_access import (  # noqa: E402
    evaluate_probe_response, is_source_failure,
)


def test_oecd_decision_binding():
    itype, bf = oecd_instrument(
        "OECD Decision C(2001)107/FINAL on the control of transboundary "
        "movements of wastes destined for recovery operations")
    assert itype == "administrative_rule" and bf == "binding"


def test_oecd_recommendation_non_binding():
    itype, bf = oecd_instrument(
        "OECD Recommendation of the Council on resource productivity")
    assert itype == "official_guidance" and bf == "non_binding"


def test_oecd_spa_detected_as_partial_not_accessible():
    body = ("<html><head><style>.match .highlight{font-weight:700}"
            "#instrument-wrapper h1{text-transform:none}</style></head>"
            "<body><div id='instrument-wrapper'></div></body></html>")
    res = evaluate_probe_response(
        source_role="OECD", endpoint_id="oecd_legalinstruments",
        official_url="https://legalinstruments.oecd.org/en/instruments",
        checked_at="2026-09-12T00:00:00+00:00", status_code=200,
        content_type="text/html", body=body,
        capabilities={"metadata": True, "fulltext": True},
        content_kind="html", detect_spa=True)
    assert res.failure_type == "SPA_JS_RENDERED"
    assert res.endpoint_status == "PARTIAL"
    assert res.metadata_available is False and res.fulltext_available is False
    assert is_source_failure("SPA_JS_RENDERED") is True


def test_spa_detection_off_keeps_accessible():
    res = evaluate_probe_response(
        source_role="X", endpoint_id="y", official_url="https://x",
        checked_at="t", status_code=200, content_type="text/html",
        body="<html><body>normal page content that is long enough</body></html>",
        capabilities={"metadata": True}, content_kind="html", detect_spa=True)
    assert res.endpoint_status == "ACCESSIBLE"      # 无 SPA 标记 → 正常可达
