# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1R §Tests：执行路由配置与选择。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ROUTING = ROOT / "ops" / "source-access-routing.yaml"


def _load():
    if not ROUTING.exists():
        pytest.skip("缺 ops/source-access-routing.yaml")
    return yaml.safe_load(ROUTING.read_text(encoding="utf-8"))


def test_routing_structure():
    d = _load()
    assert d["version"] == 1
    assert "runners" in d and "routing_rules" in d
    assert set(d["log_fields"]) == {"runner_id", "egress_region",
                                   "route_selected", "fallback_used"}


def test_blocked_jurisdictions_have_cloud_preferred():
    """原 blocked 辖区（非官方路由恢复的）preferred_runner 必须是云或浏览器。"""
    d = _load()
    rules = {tuple(sorted(r["match"].get("endpoints", []))): r
             for r in d["routing_rules"]}
    by_jid = {r["match"]["jurisdiction"]: r for r in d["routing_rules"]}
    for jid in ("BE", "US-OH", "US-MI"):
        r = by_jid[jid]
        assert r["preferred_runner"] == "runner-cloud-1", jid
        assert r["fallback"], f"{jid} 必须有 fallback 链"
    # AT/HU/US-CO 需有官方替代 fallback
    for jid in ("AT", "HU", "US-CO"):
        r = by_jid[jid]
        assert any(f.get("kind") in ("official_alt", "browser_channel")
                   for f in r["fallback"]), jid


def test_connected_jurisdictions_use_local():
    d = _load()
    by_jid = {r["match"]["jurisdiction"]: r for r in d["routing_rules"]}
    for jid in ("IT", "SK", "CZ", "US-IL", "US-TN", "US-TX", "US-NV"):
        assert by_jid[jid]["preferred_runner"] == "runner-local-dev-1", jid


def test_cloud_runner_marked_not_configured():
    d = _load()
    assert d["runners"]["runner-cloud-1"]["status"] == "not_configured"
