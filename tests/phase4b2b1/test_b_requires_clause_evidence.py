# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §4.2：B 必须有条款证据（无 → B_CANDIDATE）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.content_state import has_clause_evidence  # noqa: E402

ARTIFACT = ROOT / "outputs" / "audit" / "content_completeness.json"


def _rec(eid="e", sid="us_ecfr", title="", text="", meta=None, **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_short_text_has_no_clause_evidence():
    r = _rec(title="Hazardous waste rule", text="hazardous waste " * 5)
    assert has_clause_evidence(r) is False


def test_substantive_text_with_theme_has_clause_evidence():
    r = _rec(title="Hazardous Waste Generator Improvements Rule",
             text=("hazardous waste generators must comply with manifest "
                   "and recordkeeping requirements; battery recyclers are "
                   "subject to these standards. " * 30))
    assert has_clause_evidence(r) is True


def test_artifact_b_records_flagged_candidate_without_clause():
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_content_completeness.py")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for x in d["records"]:
        if x["acceptance_class"] == "B":
            if x["clause_evidence_available"]:
                assert x["b_status"] == "confirmed"
            else:
                assert x["b_status"] == "candidate"
