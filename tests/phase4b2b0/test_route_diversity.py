# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 8 §十：Route Diversity（路线多样性）回归。

口径：独立路线 = 机制类别（A/B/C/D/N）；**同库换词只算 1 类**。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.convergence_layers import (  # noqa: E402
    ROUTES_MIN, route_families,
)

PLANS_DIR = ROOT / "sources" / "search-plans"
KNOWN = {"A", "B", "C", "D", "N"}


def _rounds(*route_ids: str) -> list[dict]:
    return [{"route_ids": list(route_ids)}]


def test_route_families_dedupes_repeated_routes():
    """同一路线跨多轮只计 1 类（同库换词同此纪律）。"""
    assert route_families(_rounds("B", "B", "B")) == ["B"]
    assert route_families(_rounds("A", "C") + _rounds("A", "C")) == ["A", "C"]


def test_route_families_accepts_round_records():
    rounds = [{"routes": [{"id": "A"}, {"id": "B"}]},
              {"routes": [{"id": "D"}]}]
    assert route_families(rounds) == ["A", "B", "D"]


def test_route_families_empty_and_garbage():
    assert route_families([]) == []
    assert route_families([{"route_ids": [None, "", "C"]}]) == ["C"]


def test_routes_min_is_three():
    assert ROUTES_MIN == 3


def _plan_docs() -> list[dict]:
    docs = []
    for fp in sorted(PLANS_DIR.glob("*.yaml")):
        doc = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        doc["_file"] = fp.name
        docs.append(doc)
    return docs


def test_all_plans_use_known_route_letters():
    for doc in _plan_docs():
        for r in doc.get("discovery_routes") or []:
            assert str(r) in KNOWN, f"{doc['_file']} 未知路线 {r}"


def test_us_wa_plan_v2_meets_diversity_min():
    doc = next(d for d in _plan_docs()
               if d.get("plan_id") == "US_WA_PLAN_V2")
    routes = [str(r) for r in doc["discovery_routes"]]
    assert len(routes) == len(set(routes)), "路线字母不得重复"
    assert len(set(routes)) >= ROUTES_MIN


def test_at_least_one_plan_reaches_min():
    hits = [d["_file"] for d in _plan_docs()
            if len(set(map(str, d.get("discovery_routes") or []))) >= ROUTES_MIN]
    assert hits, "至少一个计划应达到 ≥3 类独立路线"
