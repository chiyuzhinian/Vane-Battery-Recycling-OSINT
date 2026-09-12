# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 1：Convergence 协议回填 —— 历史只读重标记。

纪律：
    · Phase 4B-1 六个轮次零修改（artifact 内 sha256 承诺可核验）
    · legacy 轮次无论评级均不参与新协议 streak
    · 网络失败不得解释为"没有新增结果"（失败逐条入档）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.convergence_recheck import (  # noqa: E402
    ROUNDS_DIR, build_recheck, critical_sources_for_scope, scan_round_files,
    sha256_file,
)

ARTIFACT = ROOT / "outputs" / "audit" / "convergence_recheck.json"


def test_critical_sources_per_scope():
    us = critical_sources_for_scope("US_FEDERAL")
    assert "us_federal_register" in us
    eu = critical_sources_for_scope("EU_SUPRANATIONAL")
    assert "int_basel" in eu or "eur_lex" in eu


def test_legacy_rounds_marked_partial_full():
    files = scan_round_files()
    assert files, "需要存在历史轮次文件"
    rep = build_recheck(files)
    rows = {r["round_id"]: r for r in rep["rounds"]}
    # US：R1/R3 有 FR 瞬态 ConnectError（非 critical 断源）→ PARTIAL；R2 → FULL
    us1 = next(r for r in rep["rounds"] if r["round_id"].startswith("US_FEDERAL-R1"))
    us2 = next(r for r in rep["rounds"] if r["round_id"].startswith("US_FEDERAL-R2"))
    us3 = next(r for r in rep["rounds"] if r["round_id"].startswith("US_FEDERAL-R3"))
    assert us1["legacy_plan"] is True and us1["validity"] == "PARTIAL"
    assert us1["critical_degraded"] is True
    assert us2["validity"] == "FULL"
    assert us3["validity"] == "PARTIAL" and len(us3["failures"]) == 2
    # EU：三轮无失败 → FULL
    for r in rep["rounds"]:
        if r["round_id"].startswith("EU_SUPRANATIONAL"):
            assert r["validity"] == "FULL"
    # legacy 一律不可参与新协议 streak
    for r in rep["rounds"]:
        assert r["eligible_for_streak"] is False


def test_summary_counts():
    rep = build_recheck(scan_round_files())
    s = rep["summary"]
    assert s["legacy"] == s["total"] >= 6
    assert s["full"] + s["partial"] + s["invalid"] == s["total"]
    assert s["partial"] >= 2                     # US R1 / R3


def test_artifact_matches_recompute_and_history_unchanged():
    if not ARTIFACT.exists():
        pytest.skip("artifact 未生成（先跑 scripts/audit_convergence_protocol.py）")
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["protocol"] == "phase4b2a.v1"
    # 历史零改动承诺：artifact 记录的 sha256 必须与当前文件一致
    for name, digest in artifact["file_commitments"].items():
        fp = ROUNDS_DIR / name
        assert fp.exists(), f"历史轮次文件丢失：{name}"
        assert sha256_file(fp) == digest, f"历史轮次被修改：{name}"
    # 重新计算与 artifact 一致（重标记确定性）
    rep = build_recheck(scan_round_files())
    got = {r["round_id"]: (r["validity"], r["critical_degraded"])
           for r in rep["rounds"]}
    want = {r["round_id"]: (r["validity"], r["critical_degraded"])
            for r in artifact["rounds"]}
    for rid, val in want.items():
        assert got.get(rid) == val, f"重标记不确定：{rid}"
