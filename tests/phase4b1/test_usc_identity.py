# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 4：U.S. Code 身份回归（真实 govinfo 页面片段夹具）。

夹具：govinfo_usc_42_82_head.html（42 U.S.C. Chap.82 头部，官方页面 14KB 片段）
格式事实：条文清单 = two-column-analysis-style-content-left 两栏表。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.us_code import (  # noqa: E402
    is_not_found_page, parse_us_code_chapter, usc_key,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "govinfo_usc_42_82_head.html"


def _chapter():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_us_code_chapter(html, title=42, chapter="82", year="2023")


def test_chapter_identity():
    ch = _chapter()
    assert ch.key == "USC:42:chap82"
    assert ch.title == 42 and ch.chapter == "82" and ch.year == "2023"
    assert "U.S.C. Title 42" in ch.canonical_title
    assert "PUBLIC HEALTH" in ch.canonical_title.upper()


def test_sections_parsed_from_analysis_table():
    ch = _chapter()
    assert len(ch.sections) >= 10
    assert "6921" in ch.sections        # RCRA 危废核心条款
    assert "6901" in ch.sections


def test_usc_key_forms():
    assert usc_key(42, "6921") == "USC:42:6921"
    assert usc_key(42) == "USC:42"


def test_not_found_page_detection():
    assert is_not_found_page(
        "<!DOCTYPE html><html><head><title>Page Not Found | GovInfo</title>") is True
    assert is_not_found_page("<html><head><title>U.S.C. Title 42") is False


def test_parse_rejects_not_found_page():
    try:
        parse_us_code_chapter("<html><head><title>Page Not Found | GovInfo</title>",
                              title=49, chapter="51")
    except ValueError as e:
        assert "Page Not Found" in str(e) or "不存在" in str(e)
    else:  # pragma: no cover
        raise AssertionError("伪 404 必须抛 ValueError（调用方记 SOURCE_FAILURE）")
