# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 2：FR 官方身份解析回归（真实夹具：2019-03812 / 2024-09094）。

夹具来源：Federal Register API 单文档接口（公开官方数据，2026-09-12 抓取）。
§17 标注：夹具级断言；解析规则为纯函数。
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.identity_us import (  # noqa: E402
    cfr_keys, identity_fields_from_fr, parse_fr_document,
)

FIX = Path(__file__).resolve().parent / "fixtures"
TODAY = date(2026, 9, 12)


def _load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def test_phmsa_ifr_identity_from_real_fixture():
    """真实样本：PHMSA 锂电池航空运输 IFR（2019-03812）。"""
    fr = parse_fr_document(_load("fr_2019-03812.json"), today=TODAY)
    assert fr.document_number == "2019-03812"
    assert fr.citation == "84 FR 8006"
    assert fr.canonical_id == "FR:2019-03812"
    assert fr.official_identifier == "84 FR 8006"
    assert fr.fr_type == "Rule"
    assert fr.instrument_type == "administrative_rule"
    assert fr.binding_force == "binding"
    assert fr.legal_status == "effective"
    assert fr.issuer == "Transportation Department"
    assert fr.rin == ["2137-AF20"]
    assert fr.effective_on == "2019-03-06"
    assert {"title": 49, "part": "172", "chapter": None} in fr.cfr_references
    assert fr.ambiguous is False


def test_irs_final_regulations_identity():
    """真实样本：清洁车辆抵免最终法规（2024-09094，多 RIN）。"""
    fr = parse_fr_document(_load("fr_2024-09094.json"), today=TODAY)
    assert fr.canonical_id == "FR:2024-09094"
    assert fr.citation == "89 FR 37706"
    assert len(fr.rin) >= 3
    assert {"title": 26, "part": "1", "chapter": None} in fr.cfr_references
    assert fr.instrument_type == "administrative_rule"
    assert fr.legal_status == "effective"


def test_proposed_rule_is_proposal_not_effective():
    payload = {
        "document_number": "2026-00001", "citation": "91 FR 1",
        "type": "Proposed Rule", "action": "Proposed rule.",
        "regulation_id_numbers": [], "docket_ids": ["EPA-HQ-1"],
        "cfr_references": [{"title": 40, "part": "273"}],
        "agencies": [{"name": "Environmental Protection Agency"}],
        "publication_date": "2026-01-05", "html_url": "https://x",
    }
    fr = parse_fr_document(payload, today=TODAY)
    assert fr.instrument_type == "proposal"
    assert fr.binding_force == "proposal"
    assert fr.legal_status == "proposal"


def test_not_yet_effective_future_date():
    payload = {"document_number": "2027-1", "citation": "92 FR 1", "type": "Rule",
               "effective_on": "2027-01-01", "cfr_references": [],
               "agencies": [], "publication_date": "2026-12-01"}
    fr = parse_fr_document(payload, today=TODAY)
    assert fr.legal_status == "not_yet_effective"


def test_notice_type_not_guessed():
    """宽泛类型（Notice）不得猜 instrument_type（留待 Step 8 metadata 全量）。"""
    payload = {"document_number": "2026-00002", "citation": "91 FR 2",
               "type": "Notice", "cfr_references": [], "agencies": [],
               "publication_date": "2026-01-06"}
    fr = parse_fr_document(payload, today=TODAY)
    assert fr.instrument_type == "" and fr.binding_force == ""
    assert any("未映射" in s for s in fr.issues)


def test_missing_document_number_is_ambiguous():
    fr = parse_fr_document({"title": "x"}, today=TODAY)
    assert fr.ambiguous is True
    assert any("document_number" in s for s in fr.issues)


def test_cfr_keys_for_linking():
    fr = parse_fr_document(_load("fr_2019-03812.json"), today=TODAY)
    keys = cfr_keys(fr)
    assert keys[0] == "CFR:49:172"
    assert all(k.startswith("CFR:49:") for k in keys)


def test_identity_fields_are_overlay_ready():
    fr = parse_fr_document(_load("fr_2019-03812.json"), today=TODAY)
    fields = identity_fields_from_fr(fr)
    for key in ("canonical_id", "official_identifier", "fr_document_number",
                "fr_citation", "fr_type", "fr_rin", "cfr_references",
                "fr_effective_on", "identity_status"):
        assert key in fields, key
    assert fields["canonical_id"] == "FR:2019-03812"
