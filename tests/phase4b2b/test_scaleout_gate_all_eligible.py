# -*- coding: utf-8 -*-
"""Phase 4B-2B §2：eligible 全集逐一评估聚合（禁止样本代表）。

对应规格：
  for every eligible jurisdiction: evaluate evidence/domain/identity/
  routes/critical failures；任何 eligible 自身 Gate 未通过不得计入
  eligible_pass；输出 eligible_total / eligible_pass / eligible_fail。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.saturation_gates import aggregate_eligible  # noqa: E402

ARTIFACT = ROOT / "outputs" / "audit" / "scaleout_readiness.json"


def test_aggregate_all_pass():
    r = aggregate_eligible({"A": {"all_pass": True}, "B": {"all_pass": True}})
    assert r["eligible_total"] == 2
    assert r["eligible_pass"] == 2
    assert r["eligible_fail"] == 0
    assert r["all_eligible_pass"] is True
    assert r["pass_list"] == ["A", "B"]
    assert r["fail_list"] == []


def test_aggregate_one_fail_not_counted_as_pass():
    r = aggregate_eligible({"A": {"all_pass": True},
                            "B": {"all_pass": False}})
    assert r["eligible_pass"] == 1
    assert r["eligible_fail"] == 1
    assert r["pass_list"] == ["A"]
    assert r["fail_list"] == ["B"]
    assert r["all_eligible_pass"] is False


def test_aggregate_empty_is_not_pass():
    r = aggregate_eligible({})
    assert r["eligible_total"] == 0
    assert r["all_eligible_pass"] is False


def test_aggregate_all_fail():
    r = aggregate_eligible({"X": {"all_pass": False},
                            "Y": {"all_pass": False}})
    assert r["eligible_pass"] == 0
    assert r["eligible_fail"] == 2
    assert r["all_eligible_pass"] is False


def test_artifact_uses_all_eligible_gate():
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_scaleout_gate.py")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    g = d.get("eligible_gate")
    assert g is not None, "scaleout_readiness.json 必须包含 eligible_gate"
    assert g["eligible_pass"] + g["eligible_fail"] == g["eligible_total"]
    # fail 者必须在其 per-jurisdiction 明细中附 failing 原因
    for jid in g["fail_list"]:
        assert d["per_jurisdiction_preconditions"][jid]["failing"]
    # pass 者必须 all_pass=True（不得含未通过者）
    for jid in g["pass_list"]:
        assert d["per_jurisdiction_preconditions"][jid]["all_pass"] is True
    # verdict 与聚合一致：READY 不得含 fail
    if d["verdict"] == "READY":
        assert g["all_eligible_pass"] is True
