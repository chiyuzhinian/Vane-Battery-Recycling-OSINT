# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §2：OUT_OF_SCOPE 强类一律排除（不得再有 OOS+B 终态）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.domain_scope import (  # noqa: E402
    classify_domain_scope, guard_class, guarded_effective_class,
)


def _rec(eid="e", sid="us_ecfr", title="", text="", meta=None, **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_out_of_scope_kills_all_strong_classes():
    for cls in ("A1", "A2", "B"):
        assert guard_class(cls, "OUT_OF_SCOPE") == "D"
    # C/D 保持（无强类可降）
    assert guard_class("C", "OUT_OF_SCOPE") == "C"
    assert guard_class("D", "OUT_OF_SCOPE") == "D"


def test_true_out_of_scope_examples_are_d():
    # 发动机排放（历史 B 误判）→ 域判 OUT → 降 D
    r = _rec("em1", title="Control of Emissions from New Heavy-Duty Motor "
                          "Vehicles",
             text="engines and vehicles emission control " * 30)
    assert classify_domain_scope(r) == "OUT_OF_SCOPE"
    assert guarded_effective_class(r, "B") == "D"
    # 铅酸电池（域外对象）
    r2 = _rec("la1", title="Automotive lead-acid battery recycling")
    assert classify_domain_scope(r2) == "OUT_OF_SCOPE"
    assert guard_class("A2", "OUT_OF_SCOPE") == "D"


def test_hazmat_not_out_of_scope_anymore():
    """2B1 词表归位：49 CFR/RCRA 属 SUPPORTING，不再走 OUT 分支。"""
    r = _rec("haz1", title="49 CFR Part 171 — General Information, "
                           "Regulations, and Definitions")
    assert classify_domain_scope(r) == "SUPPORTING_REGULATION"
    assert guarded_effective_class(r, "B") == "B"
    r2 = _rec("rcra1", title="40 CFR Part 260 — Hazardous Waste Management "
                             "System: General")
    assert classify_domain_scope(r2) == "SUPPORTING_REGULATION"


def test_nim_capped_not_oos_b_exception():
    """NIM 封顶 C——不再存在\"OUT_OF_SCOPE 豁免\"路径。"""
    r = _rec("nim1", sid="eu_nim_be",
             title="Arrêté relatif aux véhicules hors d'usage")
    out = guarded_effective_class(r, "A2")
    assert out == "C"
