# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 7：管辖地覆盖矩阵 —— 主题五态 / 失败解决 / 产物。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.jurisdiction_coverage import (  # noqa: E402
    derive_level, topic_status, unresolved_failures,
)

ARTIFACT = ROOT / "outputs" / "audit" / "jurisdiction_coverage.json"


def _rec(title: str, text: str = "", cls: str = "C",
         eid: str = "x", sid: str = "se_sfst") -> dict:
    return {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
            "meta": {"acceptance_class": cls}}


def test_topic_status_five_states():
    rows = [_rec("Jätelaki", "tuottajavastuu ja keräysjärjestelmä jätteistä",
                 cls="C"),
            # 2B0 Step 4：强证据需过域护栏——合成记录带横向体系法案信号
            _rec("Regulation (EU) 2023/1542 on batteries",
                 "waste battery collection scheme", cls="B"),
            _rec("VAHA-luettelo", "vaarallinen jäte sekä ohtlikud jäätmed",
                 cls="C")]
    st = topic_status(rows)
    assert st["T01"] == "PARTIAL"          # 有命中但强证据在 T02
    assert st["T02"] == "COVERED"          # EN battery collection + B（域内）
    assert st["T03"] == "MISSING"          # 无命中
    assert st["T10"] == "PARTIAL"          # vaarallinen jäte 命中、无强证据
    assert set(st) and len(st) == 14


def test_topic_status_blocked_when_channel_stuck():
    st = topic_status([], stuck=True)
    assert all(v == "BLOCKED" for v in st.values())


def test_derive_level_rules():
    assert derive_level(records=4, strong=1, failures=0, covered_roles=2) == "ACTIVE"
    assert derive_level(records=3, strong=0, failures=0, covered_roles=0) == "COLLECTED"
    assert derive_level(records=0, strong=0, failures=3, covered_roles=0) == "BLOCKED"
    assert derive_level(records=0, strong=0, failures=0, covered_roles=1) == "REFERENCE"
    assert derive_level(records=0, strong=0, failures=0, covered_roles=0) == "NOT_ONBOARDED"


def test_unresolved_failures_filters_resolved_docs():
    rows = [{"evidence_id": "fi_finlex_20110646"},
            {"evidence_id": "us_wa_rcw_70a_555"}]
    fails = [
        {"jurisdiction": "FI", "doc": "20110646", "error": "ConnectError"},
        {"jurisdiction": "US-WA", "doc": "US-WA:RCW:70A.555",
         "error": "ConnectorError"},
        {"jurisdiction": "PL", "doc": "WDU20090790666",
         "error": "ConnectorBlocked"},
    ]
    out = unresolved_failures(fails, rows)
    assert len(out) == 1 and out[0]["jurisdiction"] == "PL"


def test_coverage_artifact_shape():
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_coverage.py")
    data = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    js = data["jurisdictions"]
    assert {"SE", "FI", "US-CA", "US-WA", "PL", "DE", "BE"} <= set(js)
    # 2B0 Step 4 域护栏：US-CA 证据（AB2440/PRC 42451）经核实为**泛电池**
    # （文本无 EV/traction/vehicle 信号）→ 降 C → 不得再充当 EV 强证据；
    # 该管辖地此后需以 EV 域真实文书回补（2B0 Step 6 深采）。
    assert js["US-CA"]["level"] in ("ACTIVE", "COLLECTED")
    # 2B0 Step 5：PL 经官方替代通道（Sejm ELI API）解锁 → 离开 BLOCKED；
    # ISAP 遗留失败如实保留在 failures 清单
    assert js["PL"]["level"] in ("COLLECTED", "ACTIVE")
    assert js["PL"]["failures"]                      # 遗留失败仍入档
    assert js["FI"]["level"] in ("ACTIVE", "COLLECTED")
    # 未决失败：FI 已解决 → 0
    assert not js["FI"]["failures"]
    # 主题矩阵与黑粉矩阵每管辖地齐备
    for jid, row in js.items():
        assert len(row["topics"]) == 14
        assert set(row["black_mass"]) >= {"total", "covered"}
        assert "records" in row and "identity" in row
