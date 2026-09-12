# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 1：Source Role 状态推导回归。

核心纪律（用户 2026-09-12）：
    · 单端点失败不得把角色判死（一个入口坏了 ≠ 整个官方源不可用）
    · URL 存在 ≠ COMPLETE
    · STANDARDS 角色 ceiling=PARTIAL（EU 官方引用 ≠ 标准库接入完成）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import load_endpoints, load_registry  # noqa: E402
from app.policy.source_access import derive_role_status  # noqa: E402


def _ep(eid: str, status: str, ftype: str = "NONE",
        caps: dict | None = None, checked: str = "2026-09-12T00:00:00+00:00") -> dict:
    return {"endpoint_id": eid, "endpoint_status": status, "failure_type": ftype,
            "checked_at": checked, "capabilities": caps or {},
            "metadata_available": status in ("ACCESSIBLE", "PARTIAL"),
            "fulltext_available": status == "ACCESSIBLE"}


def test_all_endpoints_blocked_role_is_blocked():
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=False,
        has_collector=False, evidence_count=0,
        endpoint_results=[_ep("a", "BLOCKED", "HTTP_403")])
    assert st.status == "BLOCKED"
    assert st.blocked_endpoints == ["a"]


def test_single_blocked_endpoint_does_not_kill_role():
    """★ OECD/CEN 模型：一个入口 403，另一个入口可达 → 角色不判死。"""
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=False,
        has_collector=False, evidence_count=0,
        endpoint_results=[_ep("oecd_main", "BLOCKED", "HTTP_403"),
                          _ep("oecd_legal", "ACCESSIBLE")])
    assert st.status != "BLOCKED"
    assert st.status == "PARTIAL"           # 可达但尚无采集器（且有 blocked 端点）
    assert st.blocked_endpoints == ["oecd_main"]
    assert "oecd_main" in st.block_reason


def test_usable_endpoint_no_blocked_is_accessible():
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=False,
        has_collector=False, evidence_count=0,
        endpoint_results=[_ep("x", "ACCESSIBLE")])
    assert st.status == "ACCESSIBLE"
    assert st.reachable == "yes"


def test_collector_with_data_becomes_connected():
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=True,
        has_collector=True, evidence_count=42,
        endpoint_results=[_ep("x", "ACCESSIBLE")])
    assert st.status == "CONNECTED"


def test_complete_requires_declaration_and_no_blocked():
    st = derive_role_status(
        declared_status="COMPLETE", sources_configured=True,
        has_collector=True, evidence_count=100,
        endpoint_results=[_ep("x", "ACCESSIBLE")])
    assert st.status == "COMPLETE"
    # 一旦有 blocked 端点 → 从 COMPLETE 降级
    st2 = derive_role_status(
        declared_status="COMPLETE", sources_configured=True,
        has_collector=True, evidence_count=100,
        endpoint_results=[_ep("x", "ACCESSIBLE"),
                          _ep("y", "BLOCKED", "TIMEOUT")])
    assert st2.status == "CONNECTED"


def test_standards_ceiling_is_partial():
    """★ STANDARDS：EU 官方引用（eu_* 可达）也不得 COMPLETE。

    ceiling=PARTIAL 的含义是「最多 PARTIAL」：只有官方引用时
    （无采集器）→ ACCESSIBLE/PARTIAL 均可，但绝不能 CONNECTED/COMPLETE。
    """
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=False,
        has_collector=False, evidence_count=0,
        endpoint_results=[_ep("eu_harmonised_standards_ref", "ACCESSIBLE")],
        status_ceiling="PARTIAL")
    assert st.status in ("ACCESSIBLE", "PARTIAL")
    assert st.status not in ("CONNECTED", "COMPLETE")
    # 即便有采集器+数据，ceiling 仍然生效
    st2 = derive_role_status(
        declared_status="COMPLETE", sources_configured=True,
        has_collector=True, evidence_count=50,
        endpoint_results=[_ep("eu_ref", "ACCESSIBLE")],
        status_ceiling="PARTIAL")
    assert st2.status == "PARTIAL"


def test_no_endpoints_falls_back_to_registry_behaviour():
    """无端点声明的角色保持 Phase 4A 行为（数据反推）。"""
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=True,
        has_collector=True, evidence_count=7, endpoint_results=None)
    assert st.status == "CONNECTED"
    assert st.reachable == "UNVERIFIED"
    st2 = derive_role_status(
        declared_status="CONNECTED", sources_configured=True,
        has_collector=True, evidence_count=0, endpoint_results=None)
    assert st2.status == "PARTIAL"


def test_all_endpoints_blocked_but_alternate_channel_has_data():
    """★ 实测模型（CalRecycle/ECHA）：直连 403 但浏览器通道有数据 → 不判死。"""
    st = derive_role_status(
        declared_status="PARTIAL", sources_configured=True,
        has_collector=True, evidence_count=12,
        endpoint_results=[_ep("calrecycle_home", "BLOCKED", "CAPTCHA")])
    assert st.status == "CONNECTED"
    assert st.blocked_endpoints == ["calrecycle_home"]
    assert "替代采集通道" in st.block_reason
    # 无替代通道数据 → 才判 BLOCKED
    st2 = derive_role_status(
        declared_status="PARTIAL", sources_configured=True,
        has_collector=True, evidence_count=0,
        endpoint_results=[_ep("calrecycle_home", "BLOCKED", "CAPTCHA")])
    assert st2.status == "BLOCKED"


def test_no_results_endpoint_counts_as_usable():
    """NO_RESULTS 端点仍可用（不是失败）。"""
    st = derive_role_status(
        declared_status="NOT_ONBOARDED", sources_configured=False,
        has_collector=False, evidence_count=0,
        endpoint_results=[_ep("search", "ACCESSIBLE", "NO_RESULTS")])
    assert st.status == "ACCESSIBLE"


def test_registry_critical_flags_present():
    reg = load_registry()
    by_code = {j.code: j for j in reg.jurisdictions}
    eu_crit = {r.role for r in by_code["EU"].source_roles if r.critical}
    us_crit = {r.role for r in by_code["US"].source_roles if r.critical}
    assert {"EURLEX_PRIMARY", "EURLEX_DELEGATED_IMPLEMENTING", "EU_OFFICIAL_JOURNAL",
            "CUSTOMS_TRADE", "STANDARDS", "BASEL", "OECD",
            "ENVIRONMENT_AGENCY"} <= eu_crit
    assert {"FEDERAL_REGISTER", "CFR_ECFR", "US_CODE", "PUBLIC_LAW", "AGENCY_RULES",
            "BIS", "CBP", "EPA", "PHMSA"} <= us_crit
    # 每个 critical 角色都必须有端点声明（Step 1 硬约束）
    eps = {r.role for r in load_endpoints().roles}
    assert (eu_crit | us_crit) <= eps
