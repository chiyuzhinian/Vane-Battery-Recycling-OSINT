# -*- coding: utf-8 -*-
"""Source Universe 回归（Phase 4A 风险 1–4）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.source_universe import (  # noqa: E402
    build_universe_rows, universe_summary, COVERED_STATES)


def test_no_role_claims_complete_without_data_or_strong_status():
    """URL 存在 ≠ complete：未接入角色必须显式 NOT_ONBOARDED（不得默认完成）。"""
    rows = build_universe_rows()
    assert rows
    bad = [r for r in rows
           if r.status in COVERED_STATES and not r.configured
           and not r.gap_reason]
    assert not bad, f"这些行没有配置源也没有说明却标记完成: {[b.source_role for b in bad]}"


def test_nim_is_not_member_state_complete():
    """NIM ≠ 成员国法律全集（风险 3）：成员国聚合覆盖不得 100%。"""
    s = universe_summary()
    assert s["MEMBER_STATES"]["pct"] < 100.0


def test_federal_register_is_not_us_complete():
    """FR ≠ 美国联邦全部（风险 4）：US 主体覆盖不得 100%。"""
    s = universe_summary()
    assert s["US"]["pct"] < 100.0


def test_blocked_roles_are_visible():
    """blocked 必须显式列出（不能算 covered）。"""
    s = universe_summary()
    for b in s["blocked"]:
        assert b["status"] == "BLOCKED"


def test_expected_not_onboarded_is_tracked():
    """未接入但要覆盖的角色必须可数（缺口可见）。"""
    s = universe_summary()
    assert isinstance(s["not_onboarded_expected"], list)
    # 当前阶段（US 州级/标准/Basel 未接入）应当非空——若为空说明在撒谎
    assert len(s["not_onboarded_expected"]) > 0
