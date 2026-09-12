# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 3：Jurisdiction Priority —— 评分与 Pilot 选择。

纪律：
    · 权重和为 1.0（测试锁定）；分数 ∈ [0,1]；确定性（同输入同输出）
    · accessibility < floor → 只能 RESERVE（不直接进 pilot——先修复通道）
    · US 州至少 2 个 policy_signal ≥ 4（A1 栖息地约束）
    · signals 必须覆盖 27 国 + 51 州（fail-fast）
"""
from __future__ import annotations

import contextlib
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import ConfigError  # noqa: E402
from app.policy.jurisdiction_priority import (  # noqa: E402
    ACCESS_SCORE, WEIGHTS, build_scores, load_signals, score_jurisdiction,
    select_pilots,
)

CSV_OUT = ROOT / "outputs" / "audit" / "jurisdiction_priority.csv"
JSON_OUT = ROOT / "outputs" / "audit" / "jurisdiction_priority.json"


@contextlib.contextmanager
def _tmp():
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as td:
        yield Path(td)


def test_weights_sum_to_one():
    assert round(sum(WEIGHTS.values()), 6) == 1.0


def test_signals_cover_all_jurisdictions():
    signals = load_signals()
    assert len(signals["eu_member_states"]) == 27
    assert len(signals["us_states"]) == 51
    assert "DE" in signals["eu_member_states"] and "US-CA" in signals["us_states"]


def test_signals_bad_value_fails_fast():
    src = (ROOT / "sources/jurisdiction-priority-signals.yaml").read_text(
        encoding="utf-8")
    bad = src.replace("US-CA: {battery_industry: 4", "US-CA: {battery_industry: 9", 1)
    with _tmp() as tmp:
        (tmp / "s.yaml").write_text(bad, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_signals(tmp / "s.yaml")


def test_score_bounds_and_determinism():
    entry = {"battery_industry": 5, "ev_market": 5, "recycling_industry": 5,
             "policy_signal": 5}
    a = score_jurisdiction("X", entry, accessibility=1.0, diversity=1.0, reuse=1.0)
    b = score_jurisdiction("X", entry, accessibility=1.0, diversity=1.0, reuse=1.0)
    assert a == b
    assert 0.0 <= a["score"] <= 1.0
    # 理论上限 0.90：完全可达时 gap-risk 分量=0（缺口增量语义）
    assert abs(a["score"] - 0.90) < 1e-9
    z = score_jurisdiction("X", {"battery_industry": 0, "ev_market": 0,
                                 "recycling_industry": 0, "policy_signal": 0},
                           accessibility=1.0, diversity=0.0, reuse=0.0)
    # 零业务信号时：仅 accessibility 分量贡献 0.10（gap-risk 分量=0）
    assert abs(z["score"] - 0.10) < 1e-9
    z2 = score_jurisdiction("X", {"battery_industry": 0, "ev_market": 0,
                                  "recycling_industry": 0, "policy_signal": 0},
                            accessibility=0.0, diversity=0.0, reuse=0.0)
    # 完全不可达时：仅 gap-risk 分量贡献 0.10
    assert abs(z2["score"] - 0.10) < 1e-9


def test_gap_risk_grows_when_inaccessible():
    entry = {"battery_industry": 3, "ev_market": 3, "recycling_industry": 3,
             "policy_signal": 3}
    good = score_jurisdiction("X", entry, accessibility=1.0, diversity=0.0, reuse=0.0)
    bad = score_jurisdiction("X", entry, accessibility=0.1, diversity=0.0, reuse=0.0)
    assert bad["source_gap_risk"] > good["source_gap_risk"]


def _fake_probe(ids_and_status):
    rows = []
    for jid, status in ids_and_status.items():
        if status == 200:
            rows.append({"id": jid, "status": 200, "spa_suspect": False})
        elif status is None:
            rows.append({"id": jid, "status": None, "error": "ConnectError"})
        else:
            rows.append({"id": jid, "status": status, "spa_suspect": False})
    return rows


def test_select_pilots_rules():
    signals = load_signals()
    probe = _fake_probe({
        "BE": 200, "SE": 200, "FI": 200, "IT": 200, "EE": 200, "CY": 200,
        "PL": 404, "HU": None, "AT": 503, "DK": 200, "HR": 200, "LV": 200,
        "GR": 200, "SI": 200, "SK": 200, "RO": 200, "LT": 200, "BG": 200,
        "IE": 200, "MT": 200, "PT": 200, "LU": 200,
        "US-CA": 200, "US-GA": 200, "US-TX": 200, "US-TN": 200, "US-NV": 200,
        "US-OH": 200, "US-CO": 200, "US-MN": 200, "US-WA": 200, "US-ME": 200,
        "US-MI": 403, "US-IL": None, "US-NY": 403, "US-AZ": 200, "US-IN": 200,
        "US-SC": 200, "US-NC": 200, "US-OR": 200, "US-VT": 200, "US-KY": 200,
    })
    scores = build_scores(signals, probe)
    pilots = select_pilots(scores)
    # EU：参考国不参与，主选 4 + stretch 1
    assert len(pilots["EU_new_pilots"]) == 4
    assert len(pilots["EU_stretch_pilots"]) == 1
    assert not ({"DE", "NL", "ES", "FR"}
                & {p["jurisdiction_id"] for p in pilots["EU_new_pilots"]})
    # 低可达性（PL 404 / HU error）不得直接进 pilot，只能进 reserve
    eu_all = {p["jurisdiction_id"] for p in pilots["EU_new_pilots"]
              + pilots["EU_stretch_pilots"]}
    assert eu_all.isdisjoint({"PL", "HU"})
    reserve_ids = {p["jurisdiction_id"] for p in pilots["EU_reserve"]}
    assert {"PL", "HU"} & reserve_ids
    # US：6 个 pilot；MI/IL/NY（<floor）进 reserve；至少 2 个 policy≥4
    assert len(pilots["US_state_pilots"]) == 6
    us_ids = {p["jurisdiction_id"] for p in pilots["US_state_pilots"]}
    assert us_ids.isdisjoint({"US-MI", "US-IL", "US-NY"})
    policy_n = sum(1 for p in pilots["US_state_pilots"]
                   if p["policy_signal"] >= 4)
    assert policy_n >= 2


def test_priority_artifacts_generated():
    if not CSV_OUT.exists() or not JSON_OUT.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_priority.py")
    import csv as _csv
    with CSV_OUT.open(encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    assert len(rows) == 27 + 51
    assert {"jurisdiction_id", "score", "accessibility",
            "official_source_accessibility"} <= set(rows[0])
    payload = __import__("json").loads(JSON_OUT.read_text(encoding="utf-8"))
    assert payload["pilots"]["EU_new_pilots"]
    assert len(payload["pilots"]["US_state_pilots"]) == 6
