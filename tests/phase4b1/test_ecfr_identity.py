# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 3：eCFR 身份回归（真实官方 XML 夹具）。

夹具：tests/phase4b1/fixtures/ecfr_40cfr273_trimmed.xml
    来源 eCFR versioner API（官方公开），2026-09-01 版本，裁剪保留前 3 个 §。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.cfr import (  # noqa: E402
    extract_fr_citations, extract_public_laws, extract_usc_citations,
    parse_part_document, part_key, section_key,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "ecfr_40cfr273_trimmed.xml"


def _part():
    xml = FIXTURE.read_text(encoding="utf-8")
    return parse_part_document(xml, title=40, part="273", currentness="2026-09-01")


def test_part_identity_and_heading():
    p = _part()
    assert p.key == "CFR:40:273"
    assert p.canonical_title.startswith("40 CFR Part 273")
    assert "UNIVERSAL WASTE" in p.canonical_title.upper()
    assert p.currentness == "2026-09-01"


def test_sections_parsed():
    p = _part()
    assert len(p.sections) == 3
    assert p.sections[0].number == "273.1"
    assert p.sections[0].heading
    assert section_key(40, "273.1") == "CFR:40:273.1"


def test_authority_parsed_without_prefix():
    p = _part()
    assert p.authority
    assert not p.authority.startswith("Authority:")
    # 权威注记里应出现 USC 引用（RCRA/Solid Waste Disposal Act）
    assert p.usc_citations, "authority 中应能抽出 U.S.C. 引用"


def test_key_helpers():
    assert part_key(49, "173") == "CFR:49:173"
    assert section_key(49, "173.185") == "CFR:49:173.185"


def test_usc_citation_extraction():
    text = ("Authority: 49 U.S.C. 5101 et seq.; 49 U.S.C. 5121; "
            "42 U.S.C. § 6921(a); Pub. L. 109-59, 119 Stat. 1144.")
    cites = extract_usc_citations(text)
    assert "49 U.S.C. 5101" in cites
    assert "49 U.S.C. 5121" in cites
    assert "42 U.S.C. 6921(a)" in cites


def test_public_law_and_fr_extraction():
    text = "See Pub. L. 98-616 and 84 FR 8006; also 89 FR 37706."
    assert extract_public_laws(text) == ["PL 98-616"]
    assert extract_fr_citations(text) == ["84 FR 8006", "89 FR 37706"]


def test_bad_xml_raises_value_error():
    try:
        parse_part_document("<not-xml", title=40, part="273")
    except ValueError as e:
        assert "XML" in str(e) or "解析" in str(e)
    else:  # pragma: no cover
        raise AssertionError("非法 XML 必须抛 ValueError（调用方记 PARSER_FAILURE）")
