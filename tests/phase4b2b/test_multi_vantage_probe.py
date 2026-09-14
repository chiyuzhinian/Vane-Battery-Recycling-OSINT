# -*- coding: utf-8 -*-
"""Phase 4B-2B Batch 1R §Tests：multi-vantage 探测产物结构。"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.network_vantage import ACCESS_STATUSES  # noqa: E402

MATRIX = ROOT / "outputs" / "audit" / "network_vantage_matrix.json"
MATRIX_CSV = ROOT / "outputs" / "audit" / "network_vantage_matrix.csv"

REQUIRED = ("runner_id", "egress_region", "network_type", "jurisdiction",
            "source_role", "endpoint", "dns_status", "tcp_status",
            "tls_status", "http_status", "content_length", "content_type",
            "access_status", "failure_reason", "checked_at")


def _load():
    if not MATRIX.exists():
        pytest.skip("需先运行 scripts/probe_network_vantage.py")
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_matrix_fields_complete():
    d = _load()
    assert d["rows"], "矩阵不得为空"
    for row in d["rows"]:
        for k in REQUIRED:
            assert k in row, f"{row.get('endpoint')} 缺字段 {k}"


def test_matrix_statuses_valid():
    d = _load()
    for row in d["rows"]:
        assert row["access_status"] in ACCESS_STATUSES, row["access_status"]


def test_matrix_covers_all_batch1_jurisdictions():
    d = _load()
    jids = {r["jurisdiction"] for r in d["rows"]}
    for j in ("AT", "HU", "BE", "US-MI", "US-GA", "US-OH", "US-CO"):
        assert j in jids, f"缺少原 blocked 辖区：{j}"
    for j in ("IT", "SK", "CZ", "US-IL", "US-TN", "US-TX", "US-NV"):
        assert j in jids, f"缺少 CONNECTED 对照：{j}"


def test_matrix_csv_mirrors_json():
    d = _load()
    if not MATRIX_CSV.exists():
        pytest.skip("CSV 不存在")
    with MATRIX_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(d["rows"])
