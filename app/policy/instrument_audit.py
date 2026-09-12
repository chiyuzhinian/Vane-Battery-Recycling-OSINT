# -*- coding: utf-8 -*-
"""Instrument mismatch 分析（Phase 4B-1 Step 8）—— 纯逻辑。

原因分类（固定枚举）：
    TITLE_INSUFFICIENT       标题无类型信号（占位/编号式标题）
    NIM_METADATA_INSUFFICIENT NIM 记录缺官方文书类型元数据
    UNKNOWN_DOCUMENT_CLASS   元数据与标题规则都无法识别
    RULE_MAPPING_ERROR       规则命中但映射错类型
    SOURCE_METADATA_MISSING  源上游有官方元数据但未被消费（如 FR type）

纪律：AI 可辅助 classification，但**不得单独决定 binding force**。
"""
from __future__ import annotations

REASON_CODES = ("TITLE_INSUFFICIENT", "NIM_METADATA_INSUFFICIENT",
                "UNKNOWN_DOCUMENT_CLASS", "RULE_MAPPING_ERROR",
                "SOURCE_METADATA_MISSING")


def categorize(mismatch: dict) -> str:
    """单条 mismatch → 原因码。"""
    src = str(mismatch.get("source_id") or "")
    actual = str(mismatch.get("actual_instrument") or "unknown")
    meta_keys = set(mismatch.get("meta_keys") or [])
    title = str(mismatch.get("title") or "")

    # 规则命中但类型不符（matched != unknown 已由 actual 表达；仍有 matched 字段）
    if actual not in ("unknown", ""):
        return "RULE_MAPPING_ERROR"
    # NIM 记录无官方类型元数据
    if src.startswith("eu_nim_"):
        return "NIM_METADATA_INSUFFICIENT"
    # FR 记录带官方 type 但未被消费（修正后不应出现；保留以防回归）
    if src.startswith("us_fr_") or "type" in meta_keys:
        return "SOURCE_METADATA_MISSING"
    # 占位/编号式标题（无字母词）
    letters = sum(1 for ch in title if ch.isalpha())
    if len(title.strip()) < 8 or letters < 4:
        return "TITLE_INSUFFICIENT"
    return "UNKNOWN_DOCUMENT_CLASS"


def analyze(mismatches: list[dict]) -> dict:
    analysed = [{"reason": categorize(m), **m} for m in (mismatches or [])]
    by_reason: dict[str, int] = {}
    for m in analysed:
        by_reason[m["reason"]] = by_reason.get(m["reason"], 0) + 1
    return {
        "total": len(analysed),
        "by_reason": {k: by_reason.get(k, 0) for k in REASON_CODES},
        "mismatches": analysed,
    }
