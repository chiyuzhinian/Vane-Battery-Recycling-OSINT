# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 3：FR → codified_in → CFR 关系回归。

纪律：
    · 关系必须来自 FR 官方字段 cfr_references（不得由标题猜测）
    · 未在 eCFR 侧核验的 part 记为「未核验」（不是失败、不是缺失）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.cfr import build_fr_cfr_links, link_coverage  # noqa: E402


def _overlay() -> dict[str, dict]:
    return {
        "us_fr_2019-03812": {
            "document_number": "2019-03812",
            "fr_identity": {
                "canonical_id": "FR:2019-03812",
                "official_identifier": "84 FR 8006",
                "fr_citation": "84 FR 8006",
                "cfr_references": [
                    {"title": 49, "part": "172"},
                    {"title": 49, "part": "173"},
                ],
            },
        },
        "us_fr_2024-09094": {
            "document_number": "2024-09094",
            "fr_identity": {
                "canonical_id": "FR:2024-09094",
                "official_identifier": "89 FR 37706",
                "fr_citation": "89 FR 37706",
                "cfr_references": [{"title": 26, "part": "1"}],
            },
        },
    }


def test_links_from_official_field():
    links = build_fr_cfr_links(_overlay())
    assert len(links) == 3
    keys = {l["cfr_key"] for l in links}
    assert keys == {"CFR:49:172", "CFR:49:173", "CFR:26:1"}
    first = next(l for l in links if l["cfr_key"] == "CFR:49:172")
    assert first["relation"] == "codified_in"
    assert first["document_number"] == "2019-03812"
    assert first["citation"] == "84 FR 8006"
    assert "官方" in first["relation_evidence"]


def test_links_skip_incomplete_refs():
    overlay = {"x": {"fr_identity": {"cfr_references": [
        {"title": None, "part": "1"}, {"title": 40, "part": ""}, {"title": 40, "part": "273"}]}}}
    links = build_fr_cfr_links(overlay)
    assert [l["cfr_key"] for l in links] == ["CFR:40:273"]


def test_coverage_counts_verified_parts_only():
    links = build_fr_cfr_links(_overlay())
    cov = link_coverage(links, {"CFR:49:172", "CFR:49:173"})
    assert cov["links_total"] == 3
    assert cov["matched_links"] == 2
    assert cov["matched_pct"] == 66.7
    assert cov["unmatched_parts"] == ["CFR:26:1"]


def test_coverage_empty():
    cov = link_coverage([], {"CFR:40:273"})
    assert cov["links_total"] == 0 and cov["matched_pct"] == 0.0
