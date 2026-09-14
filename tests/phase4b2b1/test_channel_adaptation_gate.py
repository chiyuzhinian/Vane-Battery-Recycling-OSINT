# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §8：通道适配 gate（adapted ≥5/7）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

ARTIFACT = ROOT / "outputs" / "audit" / "blocked_channel_resolution.json"


def _d() -> dict:
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/proof_blocked_channels.py")
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_adapted_min_five():
    d = _d()
    assert len(d["adapted"]) >= 5
    assert {"PL", "US-KY", "US-MN", "EE", "US-GA"} <= set(d["adapted"])


def test_every_channel_traceable():
    d = _d()
    for key, row in d["channels"].items():
        assert row.get("method"), key
        assert row.get("note"), key
        assert row["status"] in ("ADAPTED",) or \
            row["status"].startswith(("BLOCKED", "PARTIAL")), key


def test_adapted_channels_have_new_sources():
    d = _d()
    for key in d["adapted"]:
        assert d["channels"][key].get("new_source"), key


def test_no_fake_adaptation_when_blocked():
    """BE 站点级受阻——不得为 gate 制造虚假 adapted。"""
    d = _d()
    assert "BE" not in d["adapted"]
    assert d["channels"]["BE"]["status"].startswith("BLOCKED")
