# -*- coding: utf-8 -*-
"""Legal Identity 回归（Phase 4A 风险 5–6）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.legal_identity import resolve_identity  # noqa: E402


def _rec(**kw) -> dict:
    base = {"evidence_id": "t1", "title": "", "text": "", "meta": {},
            "source_id": "x", "url": "https://example.org/a",
            "publish_date": "2023-07-12T00:00:00+00:00"}
    base.update(kw)
    return base


def test_old_but_effective_not_excluded():
    """老法规（2000）不因发布时间旧而被排除 —— status=effective。"""
    r = _rec(title="Directive 2000/53/EC on end-of-life vehicles",
             meta={"celex": "32000L0053", "in_force": "1"},
             source_id="eu_eurlex_battery_reg")
    idn = resolve_identity(r)
    assert idn.status == "effective"
    assert idn.jurisdiction == "EU"


def test_proposal_status():
    r = _rec(title="Proposal for a REGULATION concerning batteries and waste batteries",
             meta={"celex": "52020PC0798"}, source_id="eu_eurlex_battery_reg")
    assert resolve_identity(r).status == "proposal"


def test_nim_jurisdiction_and_id():
    r = _rec(title="Vyhláška o bateriích", source_id="eu_nim_cz",
             meta={"nim_id": "283350"})
    idn = resolve_identity(r)
    assert idn.jurisdiction == "CZ"
    assert idn.canonical_id == "NIM:283350"
    assert idn.status == "effective"


def test_missing_fields_reported():
    r = _rec(title="", meta={}, source_id="unknown_src", url="")
    idn = resolve_identity(r)
    assert idn.missing_fields
    assert not idn.available


def test_known_identifier_always_present():
    r = _rec(title="Regulation (EU) 2023/1542", meta={"celex": "32023R1542"},
             source_id="eu_eurlex_battery_reg")
    idn = resolve_identity(r)
    assert idn.official_identifier == "32023R1542"
    assert idn.canonical_id == "32023R1542"
