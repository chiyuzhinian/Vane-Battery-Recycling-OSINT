# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 2：identity hardening 构造/合并/分解测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.identity_hardening import (  # noqa: E402
    CORE_FIELDS, build_identity_v2, decompose_identity, effective_identity,
)


def _rec(sid: str, meta: dict, *, eid="e1", title="", url="", identity=None):
    r = {"evidence_id": eid, "source_id": sid, "meta": meta, "title": title,
         "url": url}
    if identity is not None:
        r["identity"] = identity
    return r


def test_de_gesetze_from_slug():
    ident = build_identity_v2(_rec("de_gesetze", {"slug": "battdg"}))
    assert ident["canonical_id"] == "DE:GIW:battdg"
    assert ident["official_identifier"] == "battdg"
    assert ident["language"] == "de" and ident["issuer"]
    assert ident["official_url"].endswith("/battdg/")


def test_nl_bwb_from_bwb_id():
    ident = build_identity_v2(_rec(
        "nl_bwb", {"bwb_id": "BWBR0006219",
                   "work_url": "https://repository.example/BWBR0006219"}))
    assert ident["canonical_id"] == "NL:BWB:BWBR0006219"
    assert ident["official_url"].endswith("BWBR0006219")


def test_es_boe_with_repealed_status():
    ident = build_identity_v2(_rec(
        "es_boe", {"boe_id": "BOE-A-2011-11827", "derogada": True,
                   "fecha_vigencia": "2011-08-05"}))
    assert ident["canonical_id"] == "ES:BOE:BOE-A-2011-11827"
    assert ident["legal_status"] == "repealed"
    assert ident["effective_date"] == "2011-08-05"


def test_fr_ademe_dataset_and_dila_title_number():
    a = build_identity_v2(_rec("fr_ademe_opendata",
                               {"dataset_id": "rep-vhu-2018"}))
    assert a["canonical_id"] == "FR:ADEME:rep-vhu-2018"
    d = build_identity_v2(_rec(
        "fr_dila", {"dataset": "LEGI"}, eid="abc123",
        title="[DILA LEGI] Décret n° 2021-950 du 16 juillet 2021"))
    assert d["canonical_id"] == "FR:LEGI:abc123"       # 本地稳定 id
    assert d["official_identifier"] == "2021-950"


def test_no_official_number_no_guess():
    assert build_identity_v2(_rec("fr_dila", {"dataset": "LEGI"},
                                  title="Code de l'environnement")) is not None
    # 无编号 → official_identifier 留空（不猜）
    ident = build_identity_v2(_rec("fr_dila", {"dataset": "LEGI"},
                                   title="Code de l'environnement"))
    assert ident["official_identifier"] == ""
    # 完全无编号字段的源 → None
    assert build_identity_v2(_rec("unknown_source", {})) is None


def test_effective_identity_merges_and_fills_url():
    r = _rec("us_wa_rcw", {"doc_key": "US-WA:RCW:70A.555"},
             url="https://app.leg.wa.gov/RCW/default.aspx?cite=70A.555",
             identity={"canonical_id": "US-WA:RCW:70A.555",
                       "official_identifier": "RCW:70A.555",
                       "issuer": "WA", "language": "en"})   # 缺 official_url
    ident = effective_identity(r)
    assert ident["official_url"].startswith("https://app.leg.wa.gov")
    assert all(ident.get(f) for f in CORE_FIELDS)


def test_decompose_splits_new_historical_discovery():
    records = [
        _rec("se_sfst", {"doc_key": "SE:SFS:2020:614", "language": "sv",
                         "discovered_by_round": "SE-R1"}, eid="n1", url="u"),
        _rec("se_sfst", {"doc_key": "SE:SFS:2008:834", "language": "sv"},
             eid="h1", url="u"),
        _rec("eu_nim_se", {}, eid="x1"),                      # discovery 层
    ]
    dec = decompose_identity(records, "SE")
    assert dec["new"]["total"] == 1 and dec["new"]["complete"] == 1
    assert dec["historical"]["total"] == 1
    assert dec["discovery_layer_excluded"] == 1


def test_real_artifact_identity_goals():
    """真实产物：new ≥95%、combined pilot ≥90%、FR dila 缺口如实。"""
    fp = ROOT / "outputs" / "audit" / "identity_completeness.json"
    if not fp.exists():
        pytest.skip("需先运行 scripts/audit_identity_completeness.py")
    d = json.loads(fp.read_text(encoding="utf-8"))
    js = d["jurisdictions"]
    for jid in ("SE", "FI", "US-CA", "US-WA"):
        assert js[jid]["after"]["pct"] >= 90.0, jid
        nn = js[jid]["decomposition"]["new"]
        if nn["total"]:
            assert nn["pct"] >= 95.0, jid
    # 参考管辖地：v2 构造后 ≥90%（DE/NL/ES 100%）
    for jid in ("DE", "NL", "ES"):
        assert js[jid]["after"]["pct"] >= 90.0, jid
    # FR dila：缺官方编号的条目如实未达 100%
    assert js["FR"]["after"]["pct"] >= 70.0
