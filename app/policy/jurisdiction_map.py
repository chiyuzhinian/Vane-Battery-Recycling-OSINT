# -*- coding: utf-8 -*-
"""Jurisdiction Map（Phase 4B-2A Step 2）—— 记录级管辖归属。

背景：backfill.region_of() 只能分 EU/US/OTHER —— 会把未来所有州级/成员国
记录吞进 "US"/"EU"。本模块提供 `jurisdiction_of(record)`：

    us_ca_*        → US-CA（州级，必须优先于 us_ 前缀匹配）
    us_federal_*   → US
    de_gesetze     → DE ｜ nl_bwb → NL ｜ es_boe → ES ｜ fr_dila → FR
    eu_nim_de      → DE（NIM 归属国 = 后缀）｜ eu_nim_* → 国家代码
    browser_calrecycle → US-CA ｜ browser_netherlands → NL ｜ browser_echa → EU
    int_*          → GLOBAL ｜ eu_eurlex_*/eur_lex → EU
    其余回退 backfill.region_of()

纪律（测试锁定）：
    · us_ca_* 不得被判成 US（联邦口径污染防护）
    · NIM 记录归属其国家（NIM = discovery layer，不是 corpus —— 但归属成立）
"""
from __future__ import annotations

import re

_NIM_RE = re.compile(r"^eu_nim_([a-z]{2})")

#: 显式特殊通道映射
_SPECIAL = {
    "browser_calrecycle": "US-CA",
    "browser_netherlands": "NL",
    "browser_phmsa": "US",
    "browser_bci": "US",
    "browser_echa": "EU",
}

#: 固定前缀（非契约国家）
_FIXED_PREFIXES = {
    "int_": "GLOBAL",
    "eu_eurlex_": "EU",
    "eur_lex": "EU",
    "cbp_cross": "US",
    "us_ca_": "US-CA",
    "us_federal": "US",
    "us_ecfr": "US",
    "us_usc": "US",
    "us_plaw": "US",
}


def _contract_prefixes() -> dict[str, str]:
    """从 onboarding 契约推导 source_id 前缀 → jurisdiction_id。"""
    from app.policy.jurisdiction_onboarding import list_contracts
    out: dict[str, str] = {}
    for jid in list_contracts():
        # US-CA → us_ca_ ｜ DE → de_
        if jid.startswith("US-"):
            out["us_" + jid.split("-")[1].lower() + "_"] = jid
        else:
            out[jid.lower() + "_"] = jid
    return out


def jurisdiction_of(record: dict) -> str:
    sid = str(record.get("source_id") or "")
    m = _NIM_RE.match(sid)
    if m:
        return m.group(1).upper()
    if sid in _SPECIAL:
        return _SPECIAL[sid]
    # 州级必须优先于联邦前缀：按前缀长度降序匹配
    table = dict(_FIXED_PREFIXES)
    table.update(_contract_prefixes())
    for prefix, jid in sorted(table.items(), key=lambda kv: -len(kv[0])):
        if sid.startswith(prefix):
            return jid
    from app.policy.backfill import region_of
    region = region_of(record)
    return {"EU": "EU", "US": "US"}.get(region, "GLOBAL")


def records_of(records: list[dict], jid: str) -> list[dict]:
    return [r for r in records if jurisdiction_of(r) == jid]
