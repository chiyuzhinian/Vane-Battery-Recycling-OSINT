# -*- coding: utf-8 -*-
"""Gold Set 评估回归。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.goldset import GOLDSET, evaluate  # noqa: E402


def _cases() -> list[dict]:
    return yaml.safe_load(GOLDSET.read_text(encoding="utf-8"))["cases"]


def test_goldset_size_and_holdout_ratio():
    cases = _cases()
    assert len(cases) >= 20, "Gold Set 至少 20 条"
    holdout = [c for c in cases if c.get("holdout")]
    assert len(holdout) / len(cases) >= 0.2, "holdout 至少 20%"


def test_goldset_required_fields():
    for c in _cases():
        assert c.get("id") and c.get("jurisdiction")
        assert c.get("expected_class") in ("A1", "A2", "B", "C", "D")
        assert c.get("must_find"), f"{c['id']} 缺少 must_find"


def test_evaluate_runs_and_marks_insufficient_honestly():
    res = evaluate(include_holdout=True)
    assert "INSUFFICIENT_GOLDSET" in res
    assert 0.0 <= res["precision"] <= 1.0
    assert 0.0 <= res["recall"] <= 1.0
    # §17：不得用假数据宣布 PASS —— 若案例匹配不足必须标记
    if res["cases_found"] < res["cases_total"]:
        assert res["details"]
