# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 4：Public Law 身份与 PL→USC 关系回归（真实 govinfo 页面片段夹具）。

夹具：govinfo_plaw_117_169_head.html（IRA 头部 9KB，官方页面片段）
纪律：关系必须来自官方文本（"to amend title N, United States Code" / U.S.C. 引用）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.us_code import (  # noqa: E402
    build_cfr_usc_links, parse_public_law, pl_key, pl_relations,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "govinfo_plaw_117_169_head.html"


def _pl():
    return parse_public_law(FIXTURE.read_text(encoding="utf-8"))


def test_public_law_identity():
    pl = _pl()
    assert pl.congress == 117 and pl.number == 169
    assert pl.key == "PL:117-169"
    assert pl.stat_citation == "136 STAT. 1818"
    assert pl.heading
    assert pl.usc_mentions, "IRA 文本应含 U.S.C. 引用"


def test_pl_to_usc_relations_are_evidence_based():
    rels = pl_relations(_pl())
    assert rels, "PL→USC 关系不得为空"
    relations = {r["relation"] for r in rels}
    assert relations <= {"AMENDS", "CODIFIED_AS"}
    for r in rels:
        assert r["from_key"] == "PL:117-169"
        assert r["to_key"].startswith("USC:")
        ev = r["relation_evidence"]
        assert ("文本" in ev) or ("NOTE" in ev) or ("注记" in ev)


def test_amend_relation_targets_usc_title():
    rels = [r for r in pl_relations(_pl()) if r["relation"] == "AMENDS"]
    assert rels, "IRA 应产生 AMENDS 关系（title 级或 NOTE 注记段落级）"
    # IRA 主要修订 title 26（税收）等；NOTE 注记给出段落级目标（如 USC:26:55）
    assert any(r["to_key"].startswith("USC:26") for r in rels)
    assert any("NOTE" in r["relation_evidence"] or "text" in r["relation_evidence"]
               or "文本" in r["relation_evidence"] for r in rels)


def test_pl_key_form():
    assert pl_key(117, 58) == "PL:117-58"


def test_missing_header_raises():
    try:
        parse_public_law("<html><body>no header</body></html>")
    except ValueError as e:
        assert "Congress" in str(e) or "PLAW" in str(e)
    else:  # pragma: no cover
        raise AssertionError("缺少 PL 头必须抛 ValueError")


def test_cfr_to_usc_links_from_authority_note():
    """CFR → AUTHORIZED_BY → USC（eCFR AUTH 注记桥）。"""
    records = [{
        "evidence_id": "us_ecfr_42_82",
        "meta": {"cfr_key": "CFR:40:260",
                 "usc_citations": ["42 U.S.C. 6921", "42 U.S.C. 6912"]},
    }]
    links = build_cfr_usc_links(records)
    assert {l["to_key"] for l in links} == {"USC:42:6921", "USC:42:6912"}
    assert all(l["relation"] == "AUTHORIZED_BY" for l in links)
    assert all("AUTH" in l["relation_evidence"] for l in links)
