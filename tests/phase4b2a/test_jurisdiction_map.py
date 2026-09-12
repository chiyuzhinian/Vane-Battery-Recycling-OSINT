# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 2：记录级管辖归属 jurisdiction_of()。

纪律（规格）：us_ca_* 不得判成 US（联邦口径污染防护）；
NIM 记录归属其国家（discovery layer 归属成立，但仍非 corpus）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.jurisdiction_map import jurisdiction_of, records_of  # noqa: E402


def _rec(source_id: str, **extra) -> dict:
    return {"source_id": source_id, **extra}


def test_nim_records_map_to_country():
    assert jurisdiction_of(_rec("eu_nim_de")) == "DE"
    assert jurisdiction_of(_rec("eu_nim_cz")) == "CZ"
    assert jurisdiction_of(_rec("eu_nim_pl")) == "PL"


def test_reference_national_sources_map_to_country():
    assert jurisdiction_of(_rec("de_gesetze")) == "DE"
    assert jurisdiction_of(_rec("nl_bwb")) == "NL"
    assert jurisdiction_of(_rec("es_boe")) == "ES"
    assert jurisdiction_of(_rec("fr_dila")) == "FR"
    assert jurisdiction_of(_rec("fr_ademe_opendata")) == "FR"


def test_us_state_prefix_beats_federal_prefix():
    # 州级前缀必须优先：us_ca_* 不得判成 US
    assert jurisdiction_of(_rec("us_ca_leginfo")) == "US-CA"
    assert jurisdiction_of(_rec("us_ca_calrecycle")) == "US-CA"
    assert jurisdiction_of(_rec("us_mi_egle")) == "US"  # 无 MI 契约 → 联邦回退（不误判 CA）


def test_us_federal_sources_map_to_us():
    assert jurisdiction_of(_rec("us_federal_register")) == "US"
    assert jurisdiction_of(_rec("us_ecfr")) == "US"
    assert jurisdiction_of(_rec("us_usc")) == "US"
    assert jurisdiction_of(_rec("cbp_cross")) == "US"


def test_eu_and_global_sources():
    assert jurisdiction_of(_rec("eu_eurlex_battery_reg")) == "EU"
    assert jurisdiction_of(_rec("eur_lex")) == "EU"
    assert jurisdiction_of(_rec("int_basel")) == "GLOBAL"


def test_browser_channels():
    assert jurisdiction_of(_rec("browser_calrecycle")) == "US-CA"
    assert jurisdiction_of(_rec("browser_netherlands")) == "NL"
    assert jurisdiction_of(_rec("browser_echa")) == "EU"
    assert jurisdiction_of(_rec("browser_phmsa")) == "US"


def test_records_of_filters():
    records = [_rec("eu_nim_de"), _rec("de_gesetze"), _rec("eu_nim_nl"),
               _rec("int_basel")]
    de = records_of(records, "DE")
    assert len(de) == 2
    assert all(r["source_id"] in ("eu_nim_de", "de_gesetze") for r in de)
    assert len(records_of(records, "NL")) == 1
    assert len(records_of(records, "GLOBAL")) == 1
