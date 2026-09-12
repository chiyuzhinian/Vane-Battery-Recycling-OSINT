# -*- coding: utf-8 -*-
"""Legal Family Graph 回归（Phase 4A 风险 11）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.legal_graph import (  # noqa: E402
    P0_ROOTS, build_family_status, _mentions_root)


def test_roots_defined():
    assert "32023R1542" in P0_ROOTS
    assert "32024R1157" in P0_ROOTS


def test_mentions_root_detects_number_and_nim():
    r1 = {"title": "Commission Delegated Regulation supplementing Regulation (EU) 2023/1542",
          "meta": {}, "source_id": "eu_eurlex_battery_reg"}
    assert _mentions_root(r1, "32023R1542")
    r2 = {"title": "Batterieverordnung", "meta": {"directive": "32006L0066"},
          "source_id": "eu_nim_de"}
    assert _mentions_root(r2, "32006L0066")
    r3 = {"title": "Unrelated act", "meta": {}, "source_id": "x"}
    assert not _mentions_root(r3, "32023R1542")


def test_family_status_shape_and_unresolved_blocks():
    statuses = {s.root_act: s for s in build_family_status()}
    assert set(statuses) == set(P0_ROOTS)
    for s in statuses.values():
        assert 0.0 <= s.family_completeness <= 1.0
        # unresolved 必须可被饱和门读到（风险 11：家族未解决不能 saturated）
        assert isinstance(s.unresolved_relations, list)


def test_battery_regulation_family_has_members():
    s = next(x for x in build_family_status() if x.root_act == "32023R1542")
    assert s.members_total > 0, "电池法家族必须至少有成员（否则家族扩张失效）"
