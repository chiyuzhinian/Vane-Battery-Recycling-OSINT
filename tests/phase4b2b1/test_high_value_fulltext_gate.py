# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §15：高价值全文 gate（A1/A2/B ≥95%）与失败如实性。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.saturation_gates import evidence_gate  # noqa: E402

ARTIFACT = ROOT / "outputs" / "audit" / "content_completeness.json"


def _summary() -> dict:
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_content_completeness.py")
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))["summary"]


def test_gate_function_shape():
    ok = evidence_gate({"A1": {"fulltext_pct": 100.0},
                        "A2": {"fulltext_pct": 96.0},
                        "B": {"fulltext_pct": 97.0, "clause_pct": 97.0}})
    assert ok["ok"] is True
    bad = evidence_gate({"A1": {"fulltext_pct": 100.0},
                         "A2": {"fulltext_pct": 80.0},
                         "B": {"fulltext_pct": 97.0, "clause_pct": 97.0}})
    assert bad["ok"] is False
    assert any("A2" in m for m in bad["missing"])


def test_real_artifact_a1_and_b_meet_gate():
    s = _summary()
    assert s["A1"]["fulltext_pct"] >= 95.0
    assert s["B"]["fulltext_pct"] >= 95.0
    assert s["B"]["clause_pct"] >= 95.0


def test_real_artifact_a2_gap_is_explained():
    """A2 全文不足时必须有 FETCH_FAILED 记录说明（EUR-Lex 故障如实）。"""
    s = _summary()
    if s["A2"]["fulltext_pct"] >= 95.0:
        return
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    ff = [r for r in d["records"] if r["content_state"] == "FETCH_FAILED"]
    assert len(ff) >= 30, "缺口必须伴随如实失败记录"


def test_backfill_queue_priorities():
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    for x in d["backfill_queue"]:
        assert x["backfill_status"] in ("P0", "P1", "P2")
        if x["acceptance_class"] in ("A1", "A2", "B"):
            assert x["backfill_status"] == "P0"
