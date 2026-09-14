# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §15：content_state 六态模型回归。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.content_state import (  # noqa: E402
    CONTENT_STATES, classify_content_state, needs_fulltext,
)


def _rec(eid="e", sid="us_ecfr", title="", text="", meta=None, **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_states_enum():
    assert set(CONTENT_STATES) == {
        "FULLTEXT", "METADATA_ONLY", "PLACEHOLDER", "FETCH_FAILED",
        "PAYWALLED_KNOWN", "NOT_APPLICABLE"}


def test_fulltext_by_length():
    r = _rec(text="x " * 400)
    assert classify_content_state(r) == "FULLTEXT"


def test_celex_short_is_placeholder():
    r = _rec(sid="eu_eurlex_battery_reg", text="EU legislation CELEX ...",
             meta={"celex": "32023R1542"})
    assert classify_content_state(r) == "PLACEHOLDER"


def test_explicit_states_win():
    r = _rec(text="short", meta={"content_state": "FETCH_FAILED"})
    assert classify_content_state(r) == "FETCH_FAILED"
    r2 = _rec(text="short", meta={"content_state": "PAYWALLED_KNOWN"})
    assert classify_content_state(r2) == "PAYWALLED_KNOWN"


def test_http_403_is_not_paywalled():
    """纪律：403 不得自动 = PAYWALLED_KNOWN（需显式确认）。"""
    r = _rec(sid="us_wa_rcw", text="short", meta={"http_status": 403})
    assert classify_content_state(r) != "PAYWALLED_KNOWN"


def test_non_document_line_is_not_applicable():
    r = _rec(sid="cninfo_1224918891", text="短公告")
    assert classify_content_state(r) == "NOT_APPLICABLE"


def test_short_instrument_rule():
    r = _rec(sid="eu_eurlex_battery_reg", text="更正文本" * 50,
             meta={"celex": "32023R1542R(01)", "short_instrument": True})
    assert classify_content_state(r) == "FULLTEXT"


def test_needs_fulltext_only_high_value():
    r = _rec(text="short", meta={"celex": "X"})
    assert needs_fulltext(r, "A2") is True
    assert needs_fulltext(r, "B") is True
    assert needs_fulltext(r, "C") is False
    assert needs_fulltext(r, "D") is False
