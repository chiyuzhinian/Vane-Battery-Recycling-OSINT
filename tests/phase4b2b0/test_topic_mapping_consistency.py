# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 3：主题提取/聚合一致性测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.topic_audit import (  # noqa: E402
    PLACEHOLDER_MAX_CHARS, audit_topic_mapping, effective_class,
    extract_topics_full, is_placeholder,
)


def _rec(eid="e1", sid="eu_eurlex_fulltext", title="", text="", meta=None,
         **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_extract_topics_full_catches_tail_keyword():
    """extractor gap 核心：关键词在 1600 字符之外仍可被全文本捕获。"""
    padding = ("lorem ipsum dolor sit amet " * 90)[:2000]
    text = padding + "\n waste battery collection scheme applies"
    rec = _rec(text=text)
    topics_full = extract_topics_full(rec)
    assert "T02" in topics_full
    # 分类器短窗（title + text[:1600]）检不到 —— 概念对照
    from app.policy.acceptance import scan_topics
    topics_short = scan_topics(rec["title"] + "\n" + rec["text"][:1600])[0]
    assert "T02" not in topics_short


def test_is_placeholder_boundary():
    assert is_placeholder(_rec(text="x" * (PLACEHOLDER_MAX_CHARS - 1)))
    assert not is_placeholder(_rec(text="x" * (PLACEHOLDER_MAX_CHARS + 1)))
    assert PLACEHOLDER_MAX_CHARS == 600


def test_effective_class_priority():
    with_meta = _rec(meta={"acceptance_class": "B"})
    assert effective_class(with_meta) == "B"
    # 无 meta 分类 → 现算；NIM 泛电池语境 → A2 经域护栏降到 C（Step 4）
    nim = _rec(sid="eu_nim_se", text="waste batteries recycling scheme")
    nim["relevant"] = True
    assert effective_class(nim) == "C"
    # overlay 回退优先于现算（且 OUT_OF_SCOPE 不降 B/C）
    ov = {"e1": {"acceptance_class": "C"}}
    assert effective_class(_rec(eid="e1", text="x"), ov) == "C"


def test_audit_topic_mapping_decomposes_gaps():
    records = [
        _rec(eid="ph1", text="short placeholder"),                 # placeholder
        _rec(eid="bf1", title="Waste battery collection scheme",
             text="waste batteries and recycling " * 60),          # backfill
        _rec(eid="ok1", meta={"acceptance_class": "B",
                              "topic_ids": ["T02"]},
             title="Battery recycling", text="battery recycling " * 50),
    ]
    out = audit_topic_mapping(records)
    s = out["summary"]
    assert s["total"] == 3
    assert s["placeholder_no_text"] == 1
    # bf1 与 ok1 均无 meta？ok1 有 meta；bf1 无 → backfill_gap ≥1
    assert s["backfill_gap"] >= 1
    # ok1 的 meta topic 与全文口径不一致时计 aggregation/extractor
    assert s["aggregation_gap"] >= 1


def test_real_artifact_topic_mapping():
    fp = ROOT / "outputs" / "audit" / "topic_mapping_mismatches.json"
    if not fp.exists():
        pytest.skip("需先运行 scripts/audit_topic_mapping_consistency.py")
    d = json.loads(fp.read_text(encoding="utf-8"))
    s = d["summary"]
    assert s["total"] > 3000
    # 全文本分布应覆盖全部 14 主题（修复后）
    dist = s["topics_full_distribution"]
    assert len(dist) == 14
    # EU 全文接入后：EU 全文口径主题 ≥ 10
    eu = d["per_jurisdiction"].get("EU") or {}
    assert len(eu.get("full_topics") or []) >= 10
    # 缺口分解键齐备（规格 §八 四类 + strong_no_topic）
    for k in ("placeholder_no_text", "backfill_gap", "extractor_window_gap",
              "aggregation_gap", "strong_no_topic"):
        assert k in s
