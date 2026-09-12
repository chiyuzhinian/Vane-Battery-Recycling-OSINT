# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 1：source-endpoints.yaml 配置回归。

fail-fast 纪律：
    · 端点角色必须在 jurisdiction-registry 中存在（防拼写漂移）
    · critical 角色必须有端点声明
    · content_kind / metadata_source_type 必须闭集
    · 同角色内 endpoint id 不得重复
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import (  # noqa: E402
    config_status, load_endpoints, load_registry,
)

VALID_PROBE_KINDS = {"http_ping", "json_api", "html_page", "download_head"}


def test_config_status_ok():
    status = config_status()
    assert status["ok"] is True, status["errors"]


def test_endpoint_roles_exist_in_registry():
    reg = load_registry()
    registry_roles = {r.role for j in reg.jurisdictions for r in j.source_roles}
    eps = load_endpoints()
    unknown = [r.role for r in eps.roles if r.role not in registry_roles]
    assert unknown == [], f"端点配置含未知角色（拼写漂移？）：{unknown}"


def test_every_endpoint_is_wellformed():
    eps = load_endpoints()
    assert eps.roles, "source-endpoints.yaml 不得为空"
    for role in eps.roles:
        ids = [e.id for e in role.endpoints]
        assert len(ids) == len(set(ids)), f"{role.role} 端点 id 重复：{ids}"
        for e in role.endpoints:
            assert e.official_url.startswith("https://"), (role.role, e.id)
            assert e.content_kind in ("html", "json", "xml", "pdf")
            assert e.probe.kind in VALID_PROBE_KINDS, (role.role, e.id, e.probe.kind)
            if e.probe.kind == "json_api":
                assert e.content_kind == "json", (role.role, e.id)


def test_critical_roles_have_endpoints():
    reg = load_registry()
    critical = {r.role for j in reg.jurisdictions for r in j.source_roles
                if r.critical}
    with_eps = {r.role for r in load_endpoints().roles if r.endpoints}
    missing = critical - with_eps
    assert missing == set(), f"critical 角色缺少端点声明：{missing}"


def test_standards_role_has_partial_ceiling_and_reference_types():
    eps = load_endpoints()
    std = next(r for r in eps.roles if r.role == "STANDARDS")
    assert std.status_ceiling == "PARTIAL"          # ★ 用户裁定
    types = {e.metadata_source_type for e in std.endpoints}
    assert "EU_OFFICIAL_REFERENCE" in types
    assert "OFFICIAL_PUBLISHER" in types
    # JRC 引用也可单独标记
    assert "JRC_REFERENCE" in types


def test_json_probe_endpoints_declare_expect_keys():
    """JSON 端点应声明 expect_keys（否则 SCHEMA_DRIFT 检测失效）。"""
    for role in load_endpoints().roles:
        for e in role.endpoints:
            if e.probe.kind == "json_api":
                assert e.probe.expect_keys, f"{role.role}/{e.id} 未声明 expect_keys"


def test_oecd_has_reachable_and_blocked_endpoint_pair():
    """OECD 模型：主站 403 + 子域可达，两者都要在配置里。"""
    oecd = next(r for r in load_endpoints().roles if r.role == "OECD")
    domains = {e.official_domain for e in oecd.endpoints}
    assert "legalinstruments.oecd.org" in domains
    assert "oecd.org" in domains


def test_us_code_has_alternative_channel():
    """US_CODE：uscode.house.gov 之外必须有官方替代（govinfo）。"""
    usc = next(r for r in load_endpoints().roles if r.role == "US_CODE")
    domains = {e.official_domain for e in usc.endpoints}
    assert "www.govinfo.gov" in domains
    assert "uscode.house.gov" in domains
