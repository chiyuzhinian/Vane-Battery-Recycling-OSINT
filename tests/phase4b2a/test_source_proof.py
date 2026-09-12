# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 4：Source Proof —— 能力矩阵与限制记录。

纪律（规格 §十二）：
    · Source proof 完成 = 文档化能力（允许能力为 false + limitation），
      不是"所有能力必须为真"；
    · 检索尝试 200 但 0 链接 = 能力受限记录（NO_RESULTS ≠ SOURCE_FAILURE）；
    · 样本必须真实抓取（失败要记录 error，不得伪造 URL）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.source_proof import (  # noqa: E402
    MIN_FULLTEXT_BYTES, SampleEvidence, SearchEvidence, build_limitations,
    derive_capabilities,
)

PROOFS = ROOT / "outputs" / "audit" / "source_proofs"
PILOTS = ("SE", "PL", "BE", "FI", "EE")


def test_fulltext_requires_real_text():
    small = [SampleEvidence(url="u", status=200, bytes=MIN_FULLTEXT_BYTES - 1)]
    big = [SampleEvidence(url="u", status=200, bytes=MIN_FULLTEXT_BYTES + 1)]
    assert derive_capabilities([], small)["fulltext_available"] is False
    assert derive_capabilities([], big)["fulltext_available"] is True


def test_metadata_requires_title():
    no_title = [SampleEvidence(url="u", status=200, bytes=5000, title="")]
    with_title = [SampleEvidence(url="u", status=200, bytes=5000, title="SFS 2008:834")]
    assert derive_capabilities([], no_title)["metadata_available"] is False
    assert derive_capabilities([], with_title)["metadata_available"] is True


def test_search_requires_extracted_links():
    empty = [SearchEvidence(url="s", status=200, links_extracted=0)]
    found = [SearchEvidence(url="s", status=200, links_extracted=3,
                            keyword_matched=True)]
    nav_only = [SearchEvidence(url="s", status=200, links_extracted=3,
                               keyword_matched=False)]
    assert derive_capabilities(empty, [])["search_available"] is False
    assert derive_capabilities(found, [])["search_available"] is True
    # 链接存在但未过主题核验（导航/列表）→ 不得计检索能力
    assert derive_capabilities(nav_only, [])["search_available"] is False


def test_enumeration_from_entry_links():
    assert derive_capabilities([], [], entry_links=2)["enumeration_available"] is True
    assert derive_capabilities([], [], entry_links=0)["enumeration_available"] is False


def test_limitations_record_failures_and_empty_searches():
    lim = build_limitations(
        [SearchEvidence(url="s1", status=200, links_extracted=0),
         SearchEvidence(url="s2", error="ConnectTimeout")],
        [SampleEvidence(url="d", error="ConnectError"),
         SampleEvidence(url="d2", status=404)])
    text = " ".join(lim)
    assert "无可解析文书链接" in text
    assert "ConnectTimeout" in text
    assert "ConnectError" in text
    assert "404" in text


def test_no_failure_means_no_limitations():
    lim = build_limitations([SearchEvidence(url="s", status=200,
                                            links_extracted=5,
                                            keyword_matched=True)],
                            [SampleEvidence(url="d", status=200, bytes=9000)])
    assert lim == []


def test_pilot_proof_artifacts():
    missing = [j for j in PILOTS if not (PROOFS / f"{j}.json").exists()]
    if missing:
        import pytest
        pytest.skip(f"需先运行 onboard_jurisdiction_sources.py：缺 {missing}")
    se = json.loads((PROOFS / "SE.json").read_text(encoding="utf-8"))
    src = se["sources"][0]
    # 收紧后：SFST 检索未过主题核验（如实），但全文/元数据成立
    assert src["capabilities"]["fulltext_available"] is True
    assert src["capabilities"]["metadata_available"] is True
    assert src["capabilities"]["search_available"] is False
    assert any("主题核验" in x for x in src["known_limitations"])
    ok = [s for s in src["samples"] if s.get("status") == 200]
    assert len(ok) >= 3
    pl = json.loads((PROOFS / "PL.json").read_text(encoding="utf-8"))["sources"][0]
    assert pl["capabilities"]["fulltext_available"] is True     # ISAP 文书直链可读
    be = json.loads((PROOFS / "BE.json").read_text(encoding="utf-8"))["sources"][0]
    assert be["capabilities"]["search_available"] is False      # 如实受限
    assert be["known_limitations"]                              # 限制必须记录
    ee = json.loads((PROOFS / "EE.json").read_text(encoding="utf-8"))["sources"][0]
    assert ee["known_limitations"]                              # RT 检索受限记录


US_PILOTS = ("US-CA", "US-CO", "US-GA", "US-KY", "US-MN", "US-WA")


def test_us_state_proof_artifacts():
    missing = [j for j in US_PILOTS if not (PROOFS / f"{j}.json").exists()]
    if missing:
        import pytest
        pytest.skip(f"需先运行 onboard_jurisdiction_sources.py：缺 {missing}")
    ca = json.loads((PROOFS / "US-CA.json").read_text(encoding="utf-8"))["sources"][0]
    assert ca["capabilities"]["fulltext_available"] is True
    titles = " ".join(s.get("title", "") for s in ca["samples"])
    assert "AB-2440" in titles                     # 真实法案文本证据
    wa = json.loads((PROOFS / "US-WA.json").read_text(encoding="utf-8"))["sources"][0]
    assert wa["capabilities"]["fulltext_available"] is True
    assert any("70A.555" in (s.get("title") or "") + s.get("url", "")
               for s in wa["samples"])
    # CO/MN：检索链接未过主题核验 → 不计检索能力（防导航链接假阳性）
    for jid in ("US-CO", "US-MN"):
        p = json.loads((PROOFS / f"{jid}.json").read_text(encoding="utf-8"))["sources"][0]
        assert p["capabilities"]["search_available"] is False
        assert p["known_limitations"]
    ga = json.loads((PROOFS / "US-GA.json").read_text(encoding="utf-8"))["sources"][0]
    assert ga["capabilities"]["fulltext_available"] is False
    assert any("SPA" in x or "JS" in x for x in ga["known_limitations"])
    ky = json.loads((PROOFS / "US-KY.json").read_text(encoding="utf-8"))["sources"][0]
    assert ky["known_limitations"]
