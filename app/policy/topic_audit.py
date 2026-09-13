# -*- coding: utf-8 -*-
"""Topic Audit（Phase 4B-2B0 Step 3）—— 主题提取/聚合一致性。

背景（2B0 审计 Q3/P0-A2 与 §八）：
    · 聚合层只读 meta.acceptance_class（3156/3291 条无此字段）→ 矩阵贫瘠；
    · 分类器的主题扫描窗口 = title + text[:1600]（**短窗**）→ 长法规
      （电池法 351K 字符）零主题 —— extractor gap 实测坐实；
    · overlay（policy_metadata_overlay，120 行 US）无消费者。

本模块（修复层，不动分类器与历史结果）：
    effective_class(record, overlay)   现算回退的分类口径（聚合/矩阵用）
    extract_topics_full(record)        全文口径主题提取（矩阵/审计用）
    is_placeholder(record)             CELEX-only 锚点记录检测（无正文）
    audit_topic_mapping(records)       缺口分解（规格 §八 必查四类）
"""
from __future__ import annotations

#: 占位记录阈值（CELEX-only 锚点正文 ≈ 111 字符；真文书 ≥ 数千）
PLACEHOLDER_MAX_CHARS = 600


def effective_class(record: dict, overlay: dict | None = None) -> str:
    """分类口径：meta.acceptance_class → overlay → 现算 classify_record。

    终点套用 **Domain Scope Guard**（Step 4）：泛电池背景不得充当
    A1/A2/B；域外对象仅 D。域规则异常时回退未护栏值（不阻断）。
    """
    from app.policy.acceptance import classify_record
    meta_cls = str((record.get("meta") or {}).get("acceptance_class") or "")
    if meta_cls:
        cls = meta_cls
    elif overlay:
        row = overlay.get(str(record.get("evidence_id") or "")) or {}
        ov = str(row.get("acceptance_class") or "")
        cls = ov or _rejudge(record, classify_record)
    else:
        cls = _rejudge(record, classify_record)
    try:
        from app.policy.domain_scope import guarded_effective_class
        return guarded_effective_class(record, cls)
    except Exception:  # noqa: BLE001
        return cls


def _rejudge(record: dict, classify_record) -> str:
    try:
        return classify_record(record).classification
    except Exception:  # noqa: BLE001
        return "?"


def extract_topics_full(record: dict) -> list[str]:
    """全文口径主题提取（title + 全 text；与分类器的 1600 短窗区分）。"""
    from app.policy.acceptance import scan_topics
    hay = (record.get("title") or "") + "\n" + (record.get("text") or "")
    return scan_topics(hay)[0]


def is_placeholder(record: dict) -> bool:
    """CELEX-only 占位记录（正文极短）——它可作锚点，但不产主题覆盖。"""
    return len(str(record.get("text") or "").strip()) < PLACEHOLDER_MAX_CHARS


def audit_topic_mapping(records: list[dict],
                        overlay: dict | None = None) -> dict:
    """主题映射一致性审计 → 缺口分解。

    gap_type（互斥，按优先级）：
        placeholder_no_text   正文 < 600 字符（锚点记录，非提取缺陷）
        backfill_gap          meta 无 acceptance_class（历史未回填）
        extractor_window_gap  全文有主题但分类器短窗（1600）漏掉
        aggregation_gap       meta.topic_ids 空但全文主题非空
        strong_no_topic       有效强证据（A1/A2/B）且全文零主题
                               （taxonomy/对象词表候选——人工评估，不写死）
    """
    from app.policy.acceptance import classify_record
    from app.policy.jurisdiction_map import jurisdiction_of

    gaps: dict[str, list[dict]] = {
        "placeholder_no_text": [], "backfill_gap": [],
        "extractor_window_gap": [], "aggregation_gap": [],
        "strong_no_topic": [],
    }
    stats = {"total": 0}
    topic_full_count: dict[str, int] = {}
    for r in records:
        stats["total"] += 1
        jid = jurisdiction_of(r)
        eid = str(r.get("evidence_id") or "?")
        title = (r.get("title") or "")[:70]
        if is_placeholder(r):
            gaps["placeholder_no_text"].append(
                {"evidence_id": eid, "jurisdiction": jid,
                 "text_chars": len(str(r.get("text") or ""))})
            continue
        meta = r.get("meta") or {}
        meta_cls = str(meta.get("acceptance_class") or "")
        try:
            res = classify_record(r)
        except Exception:  # noqa: BLE001
            continue
        topics_full = extract_topics_full(r)
        for t in topics_full:
            topic_full_count[t] = topic_full_count.get(t, 0) + 1
        meta_topics = list(meta.get("topic_ids") or [])
        row_missing = {"evidence_id": eid, "jurisdiction": jid,
                       "acceptance_class": meta_cls or res.classification,
                       "expected_possible_topics": topics_full,
                       "actual_topics": meta_topics or res.topic_ids,
                       "title": title}
        if not meta_cls:
            gaps["backfill_gap"].append(row_missing)
        if len(topics_full) > len(res.topic_ids):
            gaps["extractor_window_gap"].append(row_missing)
        if not meta_topics and topics_full:
            gaps["aggregation_gap"].append(row_missing)
        if (meta_cls or res.classification) in ("A1", "A2", "B") \
                and not topics_full:
            gaps["strong_no_topic"].append(
                {**row_missing,
                 "missing_topic_reason": "full_text_zero_hits（taxonomy/对象词表候选）"})
    summary = {
        "total": stats["total"],
        **{k: len(v) for k, v in gaps.items()},
        "topics_full_distribution": dict(sorted(topic_full_count.items())),
    }
    return {"summary": summary,
            "gaps": {k: v[:40] for k, v in gaps.items()}}
