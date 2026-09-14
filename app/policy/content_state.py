# -*- coding: utf-8 -*-
"""Content State —— Phase 4B-2B1 §4：证据完整性状态模型。

六态（纪律：HTTP 403 ≠ PAYWALLED_KNOWN——付费墙必须有确认证据）：
    FULLTEXT        正文齐备（≥ FULLTEXT_MIN 字符）
    METADATA_ONLY   本质元数据文书（NIM 索引/状态页/检索条目）
    PLACEHOLDER     应有全文但有编号无正文（CELEX 占位/采集缺口）
    FETCH_FAILED    采集失败（网络/端点）——需要重试
    PAYWALLED_KNOWN 确认付费墙（如 SIS 标准）——不重试
    NOT_APPLICABLE  非文书（企业数据行/统计条目）

只读判定——不修改 raw 记录。
"""
from __future__ import annotations

FULLTEXT_MIN = 600

CONTENT_STATES = ("FULLTEXT", "METADATA_ONLY", "PLACEHOLDER",
                  "FETCH_FAILED", "PAYWALLED_KNOWN", "NOT_APPLICABLE")

#: 应有全文的官方源（缺正文 → PLACEHOLDER 而非 METADATA_ONLY）
FULLTEXT_EXPECTED_PREFIXES = (
    "us_ecfr", "us_federal_register", "eu_eurlex_battery_reg",
    "us_ca_leginfo", "us_wa_rcw", "us_wa_wac", "pl_sejm", "ky_krs",
    "us_ky_krs", "us_mn_revisor", "se_sfst", "fi_finlex", "fr_dila",
    "nl_bwb", "de_gesetze", "es_boe", "us_plaw", "int_basel",
    "us_gpo", "legifrance",
)

#: 非文书（企业数据线/统计）
NON_DOCUMENT_PREFIXES = ("cninfo", "eia", "eol_")


def classify_content_state(record: dict) -> str:
    """记录 → content_state（只读；显式 meta.content_state 优先）。"""
    meta = record.get("meta") or {}
    explicit = str(meta.get("content_state") or "").upper()
    if explicit in CONTENT_STATES:
        return explicit
    sid = str(record.get("source_id") or "")
    text = record.get("text") or ""
    if sid.startswith(NON_DOCUMENT_PREFIXES):
        return "NOT_APPLICABLE"
    if len(text) >= FULLTEXT_MIN:
        return "FULLTEXT"
    # 短文书（更正件/corrigendum 等天然短）——官方内容完整获取
    #   标记依据：meta.short_instrument=True（采集器在官方源成功获取后写入）
    if meta.get("short_instrument") and len(text) >= 150:
        return "FULLTEXT"
    # 短文本：区分占位 vs 本质元数据
    if meta.get("celex"):
        return "PLACEHOLDER"
    if sid.startswith(FULLTEXT_EXPECTED_PREFIXES):
        # 状态页/差集页（本质上就是元数据）
        eid = str(record.get("evidence_id") or "")
        title = (record.get("title") or "").lower()
        if eid.endswith(":status") or "status" in eid or "legislative status" in title:
            return "METADATA_ONLY"
        return "PLACEHOLDER"
    if sid.startswith("eu_nim_"):
        return "METADATA_ONLY"
    return "METADATA_ONLY"


def needs_fulltext(record: dict, acceptance_class: str) -> bool:
    """高价值记录是否缺全文（A1/A2/B 且 state 非 FULLTEXT）。"""
    if acceptance_class not in ("A1", "A2", "B"):
        return False
    return classify_content_state(record) != "FULLTEXT"


def has_clause_evidence(record: dict) -> bool:
    """条款证据判定：现算分类器 quotes 非空 ∧ 有实质正文。

    纪律：只有 title/metadata 的记录不得作 confirmed B（→ B_CANDIDATE）。
    """
    if len(record.get("text") or "") < FULLTEXT_MIN:
        return False
    try:
        from app.policy.acceptance import classify_record
        res = classify_record(record)
        return bool(res.evidence_quotes)
    except Exception:  # noqa: BLE001
        return False
