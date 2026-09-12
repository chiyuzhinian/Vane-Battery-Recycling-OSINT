# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 5：BIS / FR 文书类型回归。

纪律：
    · FR 官方 type 优先：Rule → administrative_rule/binding；Proposed Rule → proposal
    · Notice/Order 等宽泛类型**不猜**（留 Step 8）；且任何情况不得由标题臆造 regulation
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.identity_us import FR_TYPE_INSTRUMENT  # noqa: E402
from app.policy.instruments import detect_instrument  # noqa: E402


def test_fr_type_mapping_official():
    assert FR_TYPE_INSTRUMENT["Rule"] == ("administrative_rule", "binding")
    assert FR_TYPE_INSTRUMENT["Proposed Rule"] == ("proposal", "proposal")
    assert "Notice" not in FR_TYPE_INSTRUMENT      # 不猜


def test_bis_rule_is_administrative_rule():
    itype, bf = FR_TYPE_INSTRUMENT["Rule"]
    assert itype == "administrative_rule" and bf == "binding"


def test_bis_notice_not_regulation():
    """BIS 的 Notice 类文书不得被判为 regulation（含 export control 字样也不行）。"""
    title = ("Notice of Proposed Rulemaking; Export Controls on Advanced "
             "Computing and Semiconductor Manufacturing Items")
    res = detect_instrument(title)
    # proposed rulemaking → proposal（语义优先），绝不应是 regulation
    assert res.instrument_type != "regulation"


def test_ear_guidance_page_not_regulation():
    title = "Export Administration Regulations (EAR) — Bureau of Industry and Security"
    res = detect_instrument(title)
    assert res.instrument_type != "regulation"


def test_cbp_ruling_title_never_regulation():
    title = ("CBP Ruling N301234 — The tariff classification of lithium-ion "
             "battery cells from China")
    res = detect_instrument(title)
    assert res.instrument_type != "regulation"
    assert res.instrument_type != "administrative_rule"
