# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1R §Tests：Source Proof 硬门（无真实样本不得 CONNECTED）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

PROOFS = ROOT / "outputs" / "audit" / "source_proofs"
METRICS = ROOT / "outputs" / "audit" / "batch1_metrics.json"

BATCH1 = ("AT", "HU", "IT", "SK", "CZ", "BE", "US-MI", "US-GA", "US-IL",
          "US-TN", "US-TX", "US-NV", "US-OH", "US-CO")


def test_metrics_connected_requires_samples():
    """metrics 中 onboarded=True 的辖区必须有 samples_ok>=1。"""
    if not METRICS.exists():
        pytest.skip("需先运行 scripts/batch1_metrics.py")
    d = json.loads(METRICS.read_text(encoding="utf-8"))
    for jid, r in d["per_jurisdiction"].items():
        if r.get("onboarded"):
            assert r.get("samples_ok", 0) >= 1, f"{jid} 无样本却标 onboarded"
        if r.get("samples_ok", 0) == 0:
            assert not r.get("onboarded"), f"{jid} 无样本不得 onboarded"


def test_proof_connected_semantics_per_source():
    """任一 proof 的 source：样本全非 200 时不得具有 fulltext capability。"""
    if not PROOFS.exists():
        pytest.skip("无 proof 目录")
    for jid in BATCH1:
        pf = PROOFS / f"{jid}.json"
        if not pf.exists():
            continue
        d = json.loads(pf.read_text(encoding="utf-8"))
        for src in d["sources"]:
            ok = sum(1 for s in (src.get("samples") or [])
                     if s.get("status") == 200)
            if ok == 0:
                caps = src.get("capabilities") or {}
                assert not caps.get("fulltext_available"), \
                    f"{jid}/{src.get('source_id')} 无样本却 fulltext_available"


def test_batch1_proofs_exist_for_all_selected():
    for jid in BATCH1:
        assert (PROOFS / f"{jid}.json").exists(), f"缺 proof：{jid}"
