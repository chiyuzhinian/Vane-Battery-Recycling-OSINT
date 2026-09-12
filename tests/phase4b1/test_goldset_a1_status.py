# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 9：A1 Gold Set 状态与 hard 案例回归。

用户口径（2026-09-12）：
    · A1 真实不足 → 如实 INSUFFICIENT_A1_GOLDSET，绝不人工凑样
    · A1 状态需区分「语料稀少」与「源宇宙未闭合」（报告层说明）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.goldset import evaluate  # noqa: E402


def test_a1_status_fields_present_and_honest():
    gold = evaluate()
    assert "a1_verified_count" in gold and "a1_holdout_count" in gold
    assert gold["a1_goldset_status"] in ("OK", "INSUFFICIENT_A1_GOLDSET")
    if gold["a1_verified_count"] < 5:
        assert gold["a1_goldset_status"] == "INSUFFICIENT_A1_GOLDSET"
    # 不得为了让状态变绿而虚增 A1
    assert gold["a1_verified_count"] >= 0


def test_hard_b_cases_evaluate_ok():
    """新增 hard B（标题无 battery，正文约束回收）：必须被找到且分类正确。"""
    gold = evaluate()
    by_id = {d["id"]: d for d in gold["details"]}
    for cid in ("hard_b_rcra_hazardous_waste", "hard_b_hazmat_shippers"):
        assert cid in by_id, cid
        assert by_id[cid]["status"] == "OK", by_id[cid]


def test_goldset_still_complete():
    gold = evaluate()
    assert gold["cases_found"] == gold["cases_total"]
    assert gold["precision"] == 1.0 and gold["recall"] == 1.0
    assert gold["INSUFFICIENT_GOLDSET"] is False       # 24 ≥ 20 且全找到
