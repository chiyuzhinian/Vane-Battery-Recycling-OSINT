# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 5：CBP 裁定文书类型回归（真实 CROSS API 夹具）。

纪律：海关归类裁定（ruling）**不得**判为 regulation/directive/administrative_rule。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.us_trade import (  # noqa: E402
    cross_record, parse_cross_rulings, subject_matches,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "cross_search_battery.json"


def _payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_subject_filter_drops_fuzzy_matches():
    # CROSS 检索是模糊的：主题不含检索词 → 丢弃
    assert subject_matches("The tariff classification of lithium battery packs",
                           "lithium battery") is True
    assert subject_matches("The tariff classification of black liquorice",
                           "lithium battery") is False


def test_rulings_parsed_and_filtered():
    rulings = parse_cross_rulings(_payload(), term="battery")
    assert rulings, "夹具中应有含 'battery' 的裁定"
    for r in rulings:
        assert r["ruling_number"]
        assert "battery" in r["subject"].lower()
        assert r["ruling_date"]


def test_ruling_instrument_is_guidance_never_regulation():
    rulings = parse_cross_rulings(_payload(), term="battery")
    rec = cross_record(rulings[0])
    itype = rec["meta"]["instrument_type"]
    assert itype == "official_guidance"
    assert rec["meta"]["binding_force"] == "non_binding"
    assert itype not in ("regulation", "directive", "administrative_rule",
                         "delegated_act", "implementing_act")
    assert "CROSS" in rec["meta"]["instrument_source"]


def test_ruling_record_shape():
    rec = cross_record(parse_cross_rulings(_payload(), term="battery")[0])
    assert rec["evidence_id"].startswith("us_cbp_")
    assert rec["source_id"] == "cbp_cross"
    assert rec["url"].startswith("https://rulings.cbp.gov/ruling/")
    assert rec["region"] == "US"
