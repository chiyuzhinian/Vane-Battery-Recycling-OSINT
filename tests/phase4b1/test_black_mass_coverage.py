# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 10：Black Mass 六线覆盖矩阵回归。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.black_mass import (  # noqa: E402
    LINES, STATUS_ENUM, build_coverage, classify_line, gov_level,
)


def _rec(eid: str, title: str, cls: str = "B", sid: str = "us_ecfr") -> dict:
    return {"evidence_id": eid, "title": title, "source_id": sid,
            "meta": {"acceptance_class": cls}, "text": ""}


def test_six_lines_defined():
    assert len(LINES) == 6
    ids = [l[0] for l in LINES]
    assert ids == ["waste_status", "hazardous", "transport",
                   "transboundary", "customs", "end_of_waste"]


def test_line_matching():
    assert classify_line(_rec("a", "Standards for Universal Waste Management"),
                         "waste_status") is True
    assert classify_line(_rec("b", "Identification and Listing of Hazardous Waste"),
                         "hazardous") is True
    assert classify_line(_rec("c", "Shipments of waste — Regulation (EU) 2024/1157"),
                         "transboundary") is True
    assert classify_line(_rec("d", "CBP Ruling N1 — tariff classification"),
                         "customs") is True
    assert classify_line(_rec("e", "Recycling efficiency calculation"),
                         "end_of_waste") is True
    assert classify_line(_rec("f", "Nothing related"), "transport") is False


def test_coverage_status_rules():
    records = [
        _rec("t1", "49 CFR Part 173 — Shippers requirements for shipments"),
        _rec("t2", "Hazardous Materials: Enhanced Safety Provisions"),
        _rec("w1", "Batteries and waste batteries", cls="C"),   # 仅背景
    ]
    cov = build_coverage(records)
    by = {l["line_id"]: l for l in cov["lines"]}
    assert by["transport"]["status"] == "COVERED"
    assert by["waste_status"]["status"] == "PARTIAL"        # 有命中无强证据
    assert by["customs"]["status"] in ("MISSING", "BLOCKED")
    assert cov["summary"]["total"] == 6


def test_every_line_has_evidence_or_gap_reason():
    cov = build_coverage([_rec("x", "battery recycling")])
    for line in cov["lines"]:
        assert line["status"] in STATUS_ENUM
        if line["status"] != "COVERED":
            assert line["gap"], f"{line['line_id']} 缺 gap 理由"


def test_region_filter():
    records = [
        _rec("us1", "49 CFR Part 173 shipments", sid="us_ecfr"),
        _rec("eu1", "Shipments of waste Regulation 2024/1157", sid="eu_eurlex_battery_reg"),
    ]
    cov_us = build_coverage(records, region="US")
    cov_eu = build_coverage(records, region="EU")
    us_lines = {l["line_id"]: l["documents"] for l in cov_us["lines"]}
    eu_lines = {l["line_id"]: l["documents"] for l in cov_eu["lines"]}
    assert us_lines["transport"] >= 1
    assert eu_lines["transboundary"] >= 1


# ---------------- Phase 4B-2B0 Step 8：联邦/州拆分（§九）----------------

def test_gov_level_classification():
    assert gov_level(_rec("f", "x", sid="us_ecfr")) == "federal"
    assert gov_level(_rec("s", "x", sid="us_ca_leginfo")) == "state"
    assert gov_level(_rec("w", "x", sid="us_wa_wac")) == "state"
    assert gov_level(_rec("e", "x", sid="eu_eurlex_battery_reg")) == "supra"


def test_state_does_not_count_as_federal():
    """州级强证据不得冒充联邦覆盖（规格 §九）。"""
    records = [
        _rec("ca1", "Hazardous waste listing and identification",
             sid="us_ca_leginfo"),
    ]
    cov = build_coverage(records, region="US", split_level=True)
    haz = next(l for l in cov["lines"] if l["line_id"] == "hazardous")
    assert haz["status"] == "COVERED"          # 州级强证据仍算 US 覆盖
    assert haz["federal_strong"] == 0
    assert haz["state_strong"] == 1
    assert "州" in haz["level_note"] and "联邦" in haz["level_note"]


def test_split_level_reports_both_sides():
    records = [
        _rec("fed1", "Identification and Listing of Hazardous Waste",
             sid="us_ecfr"),
        _rec("st1", "Hazardous waste requirements",
             sid="us_ca_leginfo"),
    ]
    cov = build_coverage(records, region="US", split_level=True)
    haz = next(l for l in cov["lines"] if l["line_id"] == "hazardous")
    assert haz["federal_strong"] == 1
    assert haz["state_strong"] == 1
    assert haz["federal_ids"] == ["fed1"] and haz["state_ids"] == ["st1"]
    assert "不合并计数" in haz["level_note"]


def test_split_level_default_off_keeps_shape():
    """默认（split_level=False）不改变既有输出形状。"""
    cov = build_coverage([_rec("x", "battery recycling")])
    for line in cov["lines"]:
        assert "federal_strong" not in line


def test_federal_only_lines_marked_not_applicable_state_level():
    """2B1 §12：跨境/海关属联邦权限——州级 NOT_APPLICABLE，不得误判 MISSING。"""
    records = [
        _rec("t1", "Shipments of waste — Regulation (EU) 2024/1157 transboundary",
             sid="us_ecfr"),
    ]
    cov = build_coverage(records, region="US", split_level=True)
    tb = next(l for l in cov["lines"] if l["line_id"] == "transboundary")
    assert tb["state_strong"] == 0
    assert "NOT_APPLICABLE_STATE_LEVEL" in tb["level_note"]
