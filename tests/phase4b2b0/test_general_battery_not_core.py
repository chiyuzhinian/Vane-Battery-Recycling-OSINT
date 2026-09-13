# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 4：泛消费电池不得冒充 EV 核心（规格 §五 核心场景）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.domain_scope import (  # noqa: E402
    classify_domain_scope, guard_class,
)
from app.policy.topic_audit import effective_class  # noqa: E402

ARTIFACT = ROOT / "outputs" / "audit" / "domain_relevance.json"

#: 规格点名的泛消费电池语境（不得因 battery recycling/EPR/stewardship 自动 A1/A2）
GENERAL_TEXTS = [
    ("FR portable 收集安排",
     "Arrêté fixant les cas et conditions dans lesquels les piles et "
     "accumulateurs portables usagés sont collectés, avec objectifs de "
     "recyclage et de valorisation des batteries"),
    ("FI 电池与蓄电池法令",
     "Valtioneuvoston asetus paristoista ja akuista annetun "
     "valtioneuvoston asetuksen muuttamisesta; kierrätys ja tuottajavastuu "
     "koskevat kannettavia akkuja ja paristoja"),
    ("EN button cell 回收",
     "consumer button cell battery recycling and stewardship program for "
     "household batteries, with EPR obligations for producers"),
]


@pytest.mark.parametrize("label,text", GENERAL_TEXTS)
def test_general_battery_never_a1_a2(label: str, text: str):
    r = {"evidence_id": "t", "source_id": "eu_nim_test", "title": text[:80],
         "text": text, "meta": {}, "relevant": True}
    cls = classify_record(r).classification
    scope = classify_domain_scope(r)
    assert scope == "GENERAL_BATTERY_BACKGROUND", label
    final = guard_class(cls, scope)
    assert final not in ("A1", "A2"), f"{label}: {cls} → {final}"


def test_ev_text_stays_core():
    r = {"evidence_id": "t", "source_id": "eu_eurlex_battery_reg",
         "title": "Regulation (EU) 2023/1542 on batteries and waste batteries",
         "text": "traction batteries for electric vehicles must meet recycled "
                 "content targets; black mass processing",
         "meta": {"celex": "32023R1542"}, "relevant": True}
    scope = classify_domain_scope(r)
    assert scope in ("CORE_EV_TRACTION", "HORIZONTAL_APPLIES_TO_EV")
    cls = classify_record(r).classification
    assert guard_class(cls, scope) == cls          # 无降级


def test_real_artifact_guard_rules():
    if not ARTIFACT.exists():
        pytest.skip("需先运行 scripts/audit_domain_relevance.py")
    d = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    dist = d["distribution"]
    assert dist["GENERAL_BATTERY_BACKGROUND"] > 0
    assert dist["CORE_EV_TRACTION"] > 0
    # 违规（护栏改写）清单里：GENERAL 来源的降级必须落在 C
    for v in d["violations"]:
        if v["domain_scope"] == "GENERAL_BATTERY_BACKGROUND":
            assert v["class_after"] in ("C", "D"), v
        if v["domain_scope"] == "OUT_OF_SCOPE":
            assert v["class_before"] in ("A1", "A2"), v   # 仅降 A1/A2


def test_effective_class_applies_guard_for_nim_general():
    r = {"evidence_id": "t", "source_id": "eu_nim_fi",
         "title": "Valtioneuvoston asetus paristoista ja akuista",
         "text": "kannettavat paristot ja akut; kierrätys",
         "meta": {}, "relevant": True}
    assert effective_class(r) == "C"      # A2 默认路径被域护栏改写
