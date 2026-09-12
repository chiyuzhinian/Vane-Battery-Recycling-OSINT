# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 1：failure taxonomy 与 Standards 访问模型回归。

§17 标注：本文件为 FIXTURE 级断言（纯函数），不得作为系统级验收证据。
核心纪律（用户 2026-09-12）：
    · HTTP 403/500 ≠ paywalled_known
    · NO_RESULTS ≠ SOURCE_FAILURE
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.source_access import (  # noqa: E402
    FAILURE_TYPES, classify_body_signals, classify_exception,
    classify_http_status, evaluate_probe_response, is_source_failure,
    resolve_open_access_status,
)

BASE = dict(source_role="R", endpoint_id="E", official_url="https://x",
            checked_at="2026-09-12T00:00:00+00:00", content_type="text/html")


def _ev(**kw):
    params = dict(BASE)
    params.update(kw)
    return evaluate_probe_response(**params)


# ---------------------------------------------------------- 状态码

def test_status_code_mapping():
    assert classify_http_status(403) == "HTTP_403"
    assert classify_http_status(404) == "HTTP_404"
    assert classify_http_status(429) == "HTTP_429"
    assert classify_http_status(406) == "HTTP_OTHER_4XX"
    assert classify_http_status(500) == "HTTP_5XX"
    assert classify_http_status(200) == "NONE"
    assert classify_http_status(None) == "CONNECTION_ERROR"


def test_403_is_not_paywall_by_itself():
    """★ 核心纪律：ISO 403 只能记 HTTP_403，不得推断付费墙。"""
    ftype = classify_body_signals("Forbidden", status_code=403)
    assert ftype is None
    res = _ev(status_code=403, body="Forbidden")
    assert res.failure_type == "HTTP_403"
    assert res.endpoint_status == "BLOCKED"
    assert res.metadata_available is False and res.fulltext_available is False
    # 且不得进 open_access_status 的 paywalled 判定
    assert resolve_open_access_status(
        fulltext_available=res.fulltext_available,
        metadata_available=res.metadata_available,
        paywall_confirmed=res.failure_type == "PAYWALL_CONFIRMED",
    ) != "paywalled_known"


def test_403_with_api_key_marker_refined():
    res = _ev(status_code=403, body="The API key is required for this endpoint")
    assert res.failure_type == "API_KEY_REQUIRED"


def test_403_captcha_and_auth_and_robots():
    assert _ev(status_code=403, body="Please solve the captcha").failure_type == "CAPTCHA"
    assert _ev(status_code=403,
               body="Sign in to continue").failure_type == "AUTH_REQUIRED"
    assert _ev(status_code=403,
               body="Blocked by robots.txt").failure_type == "ROBOTS_RESTRICTED"


def test_paywall_confirmed_requires_explicit_mechanism():
    """明确付费机制证据（订阅短语/购买短语）→ PAYWALL_CONFIRMED。"""
    res = _ev(status_code=200, content_kind="html",
              body="Subscribe to read. This ISO standard: add to cart. CHF 128.",
              capabilities={"metadata": False, "fulltext": False})
    assert res.failure_type == "PAYWALL_CONFIRMED"
    # 付费墙属 source failure（无法以合法途径取得内容）
    assert is_source_failure(res.failure_type) is True


def test_official_free_page_is_not_paywall_false_positive():
    """★ 实测回归（2026-09-12）：EUR-Lex/Basel/JRC 免费官方页不得误判付费墙。

    原缺陷：裸词 "eur"（命中 "EUR-Lex"）+ "standard"（命中法律正文）
    导致一批官方页被判 PAYWALL_CONFIRMED。
    """
    body = ("EUR-Lex — Official Journal of the European Union. "
            "This Regulation lays down requirements for batteries. "
            "The standard approach applies. Budget: 120 000 EUR. "
            "In order to ensure compliance, the Commission shall adopt acts.")
    assert classify_body_signals(body, status_code=200, strict=True) is None
    res = _ev(status_code=200, content_kind="html", body=body,
              capabilities={"metadata": True, "fulltext": True})
    assert res.failure_type == "NONE"
    assert res.endpoint_status == "ACCESSIBLE"


def test_200_page_challenge_requires_strict_markers():
    """普通页面里的 recaptcha 脚本引用 ≠ 挑战页；真实挑战页短语才判 CAPTCHA。"""
    benign = "<script src='https://www.google.com/recaptcha/api.js'></script>" \
             "<p>Batteries Regulation overview</p>"
    assert classify_body_signals(benign, status_code=200, strict=True) is None
    challenge = "Checking your browser before accessing. Enable javascript and " \
                "cookies to continue."
    assert classify_body_signals(challenge, status_code=200,
                                 strict=True) == "CAPTCHA"


def test_price_plus_newsletter_is_not_paywall():
    """★ 实测回归：BIS EAR 页（罚款金额 + 新闻订阅）不得误判付费墙。"""
    body = ("Export Administration Regulations — civil penalty up to $250,000. "
            "Subscribe to our newsletter for updates. USD 3,112 in fees. "
            "This standard reference is free.")
    assert classify_body_signals(body, status_code=200, strict=True) is None


def test_exception_classification():
    assert classify_exception(TimeoutError("timed out")) == "TIMEOUT"

    class _SSL(Exception):
        pass
    _SSL.__name__ = "SSLError"
    assert classify_exception(_SSL("certificate verify failed")) == "TLS_FAILURE"
    assert classify_exception(
        Exception("getaddrinfo failed")) == "DNS_FAILURE"
    assert classify_exception(None) == "NONE"


# ---------------------------------------------------------- JSON 结构

def test_json_parse_failure_and_schema_drift():
    res = _ev(status_code=200, content_kind="json", body="<html>not json</html>")
    assert res.failure_type == "PARSER_FAILURE"
    assert res.endpoint_status == "BLOCKED"

    res2 = _ev(status_code=200, content_kind="json", body='{"foo": 1}',
               expect_keys=["results"])
    assert res2.failure_type == "SCHEMA_DRIFT"
    assert res2.endpoint_status == "BLOCKED"


def test_no_results_is_not_failure():
    """★ 核心纪律：请求成功 + 解析成功 + 0 条 → NO_RESULTS（非失败）。"""
    res = _ev(status_code=200, content_kind="json", body='{"results": []}',
              expect_keys=["results"], payload_empty_for="results",
              capabilities={"metadata": True, "fulltext": True})
    assert res.failure_type == "NO_RESULTS"
    assert res.endpoint_status == "ACCESSIBLE"
    assert res.reachable is True
    assert is_source_failure(res.failure_type) is False


def test_unsupported_format_pdf_without_parser():
    res = _ev(status_code=200, content_kind="pdf", content_type="application/pdf",
              capabilities={"metadata": True, "fulltext": True})
    assert res.failure_type == "UNSUPPORTED_FORMAT"
    assert res.endpoint_status == "PARTIAL"
    assert res.reachable is True
    assert res.fulltext_available is False      # 不得假装拿到全文
    assert res.metadata_available is True


# ---------------------------------------------------------- Standards 五概念

def test_open_access_status_mapping():
    assert resolve_open_access_status(
        fulltext_available=True, metadata_available=True,
        paywall_confirmed=False) == "open_fulltext"
    assert resolve_open_access_status(
        fulltext_available=False, metadata_available=True,
        paywall_confirmed=False) == "official_metadata_only"
    assert resolve_open_access_status(
        fulltext_available=False, metadata_available=False,
        paywall_confirmed=True) == "paywalled_known"
    assert resolve_open_access_status(
        fulltext_available=False, metadata_available=False,
        paywall_confirmed=False) == "unavailable"


def test_failure_type_enum_is_closed():
    assert "NO_RESULTS" in FAILURE_TYPES
    assert "PAYWALL_CONFIRMED" in FAILURE_TYPES
    assert is_source_failure("NONE") is False
