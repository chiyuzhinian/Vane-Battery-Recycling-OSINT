# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 6：Standards 访问模型回归（用户口径 2026-09-12）。

纪律：
    · 五概念分离：metadata_available / fulltext_available / open_access_status /
      metadata_source_type / endpoint_status
    · EU 官方引用（OJ/JRC）→ official_metadata_only + EU_OFFICIAL_REFERENCE
    · 无全文 → 不得生成条款证据（fail-fast）
    · HTTP 403/500 ≠ paywalled_known
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.crossborder import (  # noqa: E402
    assert_valid_standard, standard_from_official_reference,
)
from app.policy.source_access import resolve_open_access_status  # noqa: E402


def test_eu_reference_metadata_only():
    rec = standard_from_official_reference(
        title="Harmonised standards reference hub", url="https://example.eu",
        publisher="European Commission", source_type="EU_OFFICIAL_REFERENCE")
    meta = rec.as_meta()
    assert meta["metadata_available"] is True
    assert meta["fulltext_available"] is False
    assert meta["open_access_status"] == "official_metadata_only"
    assert meta["metadata_source_type"] == "EU_OFFICIAL_REFERENCE"
    assert meta["clause_evidence"] == []
    assert_valid_standard(rec)


def test_jrc_reference_type():
    rec = standard_from_official_reference(
        title="JRC repository", url="https://jrc.eu", source_type="JRC_REFERENCE")
    assert rec.as_meta()["metadata_source_type"] == "JRC_REFERENCE"


def test_invalid_source_type_rejected():
    try:
        standard_from_official_reference(title="x", url="u",
                                         source_type="NOT_A_TYPE")
    except ValueError as e:
        assert "metadata_source_type" in str(e)
    else:  # pragma: no cover
        raise AssertionError("非法 metadata_source_type 必须 fail-fast")


def test_no_fulltext_means_no_clause_evidence():
    rec = standard_from_official_reference(title="x", url="u")
    rec.clause_evidence = ["fabricated clause"]        # 人为违规
    try:
        assert_valid_standard(rec)
    except AssertionError as e:
        assert "条款证据" in str(e)
    else:  # pragma: no cover
        raise AssertionError("无全文时带条款证据必须被拒绝")


def test_http_403_is_not_paywall():
    """403 失败的端点不得被解读为付费墙。"""
    status = resolve_open_access_status(fulltext_available=False,
                                        metadata_available=False,
                                        paywall_confirmed=False)
    assert status == "unavailable"          # 不是 paywalled_known


def test_paywall_only_with_confirmation():
    assert resolve_open_access_status(
        fulltext_available=False, metadata_available=False,
        paywall_confirmed=True) == "paywalled_known"
