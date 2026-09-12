# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 6：Basel 文档阶段与约束力回归。

纪律（规格 §5）：draft technical guideline 不得当 binding regulation。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.crossborder import basel_instrument, basel_status  # noqa: E402


def test_draft_technical_guideline_is_non_binding():
    status = basel_status("Draft technical guidelines on transboundary movements "
                          "of wastes")
    assert status == "draft"
    itype, bf = basel_instrument(status)
    assert itype == "official_guidance"
    assert bf == "non_binding"          # ★ 核心纪律


def test_decision_is_binding():
    status = basel_status("Decision BC-14/12: Amendments to Annexes II, VIII...")
    assert status == "decision"
    itype, bf = basel_instrument(status)
    assert itype == "administrative_rule"
    assert bf == "binding"


def test_final_and_adopted_guidelines_still_non_binding():
    for text in ("Final technical guidelines on environmentally sound management",
                 "Adopted guidance on the identification of wastes"):
        itype, bf = basel_instrument(basel_status(text))
        assert itype == "official_guidance" and bf == "non_binding"


def test_unknown_status_defaults_to_guidance():
    itype, bf = basel_instrument(basel_status("UNEP/CHW.14/7/Add.1"))
    assert itype == "official_guidance" and bf == "non_binding"
