# -*- coding: utf-8 -*-
"""Saturation Gate 回归（Phase 4A 风险 1–4、11–12，§10）。

§17 标注：本文件全部为 FIXTURE/MOCK 级断言（纯函数），
不得作为系统级验收证据。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy import saturation  # noqa: E402
from app.policy.saturation import status_from, _discovery_routes  # noqa: E402


def test_zero_results_never_saturated():
    """风险 1：0 通过 ≠ saturated。"""
    assert status_from(0, 9) != "SATURATED"
    assert status_from(8, 9) != "SATURATED"     # 差一个也不算


def test_blocked_overrides_everything():
    """风险 2：blocked source → BLOCKED（即便全检查通过）。"""
    assert status_from(9, 9, blocked_expected=1) == "BLOCKED"


def test_all_pass_is_saturated():
    assert status_from(9, 9) == "SATURATED"


def test_single_discovery_channel_not_enough():
    """风险 12：单一发现通道不得视为饱和。"""
    records = [{"meta": {"celex": "32023R1542"}, "source_id": "eu_eurlex_battery_reg",
                "channel": "connector"}]
    fam = [type("F", (), {"found_relations": {}})()]
    routes = _discovery_routes(records, fam)
    assert routes["count"] < 3


def test_multiple_channels_counted():
    records = [
        {"meta": {"celex": "32023R1542"}, "source_id": "eu_eurlex_battery_reg",
         "channel": "connector"},
        {"meta": {}, "source_id": "eu_eurlex_keyword", "channel": "connector"},
        {"meta": {}, "source_id": "browser_phmsa", "channel": "browser_capture"},
    ]
    fam = [type("F", (), {"found_relations": {"SUPPLEMENTS": ["x"]}})()]
    routes = _discovery_routes(records, fam)
    assert routes["count"] >= 3


def test_real_evaluation_not_falsely_saturated():
    """集成冒烟：真实系统当前绝不应为 SATURATED（有已知缺口）。"""
    res = saturation.evaluate_saturation("EU")
    assert res["status"] in ("PARTIAL", "WEAK", "NEAR_SATURATED", "BLOCKED")
    assert res["status"] != "SATURATED"
