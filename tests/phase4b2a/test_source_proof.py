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
    found = [SearchEvidence(url="s", status=200, links_extracted=3)]
    assert derive_capabilities(empty, [])["search_available"] is False
    assert derive_capabilities(found, [])["search_available"] is True


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
    lim = build_limitations([SearchEvidence(url="s", status=200, links_extracted=5)],
                            [SampleEvidence(url="d", status=200, bytes=9000)])
    assert lim == []


def test_pilot_proof_artifacts():
    missing = [j for j in PILOTS if not (PROOFS / f"{j}.json").exists()]
    if missing:
        import pytest
        pytest.skip(f"需先运行 onboard_jurisdiction_sources.py：缺 {missing}")
    se = json.loads((PROOFS / "SE.json").read_text(encoding="utf-8"))
    src = se["sources"][0]
    assert src["capabilities"]["search_available"] is True      # SFST fritext 可检索
    assert src["capabilities"]["fulltext_available"] is True    # 样本 4/4
    ok = [s for s in src["samples"] if s.get("status") == 200]
    assert len(ok) >= 3
    pl = json.loads((PROOFS / "PL.json").read_text(encoding="utf-8"))["sources"][0]
    assert pl["capabilities"]["fulltext_available"] is True     # ISAP 文书直链可读
    be = json.loads((PROOFS / "BE.json").read_text(encoding="utf-8"))["sources"][0]
    assert be["capabilities"]["search_available"] is False      # 如实受限
    assert be["known_limitations"]                              # 限制必须记录
    ee = json.loads((PROOFS / "EE.json").read_text(encoding="utf-8"))["sources"][0]
    assert ee["known_limitations"]                              # RT 检索受限记录
