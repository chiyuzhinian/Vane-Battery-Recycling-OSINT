# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 10：Black Mass 六线覆盖矩阵回归。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.black_mass import (  # noqa: E402
    LINES, STATUS_ENUM, build_coverage, classify_line,
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
