# -*- coding: utf-8 -*-
"""audit_topic_mapping_consistency.py —— Step 3：主题映射一致性审计。

产物：outputs/audit/topic_mapping_mismatches.json

检查（规格 §八）：
    · document / acceptance_class / expected_possible_topics / actual_topics
      / missing_topic_reason（四类 gap：placeholder / backfill / extractor
      window / aggregation；另附 strong_no_topic 候选清单）
    · per-jurisdiction：meta 口径 vs 全文口径主题覆盖对比（不写死具体 topic）

用法：py scripts/audit_topic_mapping_consistency.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import load_jsonl, load_records  # noqa: E402
from app.policy.jurisdiction_map import jurisdiction_of  # noqa: E402
from app.policy.topic_audit import (  # noqa: E402
    audit_topic_mapping, effective_class, extract_topics_full,
)

OUT = ROOT / "outputs" / "audit" / "topic_mapping_mismatches.json"
OVERLAY = ROOT / "outputs" / "policy_metadata_overlay.jsonl"


def main() -> int:
    records = load_records(ROOT)
    overlay = load_jsonl(OVERLAY) if OVERLAY.exists() else {}
    audit = audit_topic_mapping(records, overlay)

    # per-jurisdiction：meta 口径 vs 全文口径（strong 记录的主题集）
    per_j: dict[str, dict] = {}
    for r in records:
        sid = str(r.get("source_id") or "")
        if sid.startswith("eu_nim_"):
            continue                       # discovery layer 不入 corpus 口径
        cls = effective_class(r, overlay)
        if cls not in ("A1", "A2", "B"):
            continue
        jid = jurisdiction_of(r)
        e = per_j.setdefault(jid, {"meta_topics": set(), "full_topics": set()})
        e["meta_topics"].update((r.get("meta") or {}).get("topic_ids") or [])
        e["full_topics"].update(extract_topics_full(r))
    per_j_out = {jid: {"meta_topics": sorted(v["meta_topics"]),
                       "full_topics": sorted(v["full_topics"]),
                       "delta": sorted(set(v["full_topics"])
                                       - set(v["meta_topics"]))}
                 for jid, v in sorted(per_j.items())}

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "note": ("expected_possible_topics = 全文口径扫描；actual = meta/分类器"
                 "短窗口径；缺口分解见 gaps。**不写死具体文档的最终 topic**"),
        "summary": audit["summary"],
        "gaps": audit["gaps"],
        "per_jurisdiction": per_j_out,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    s = audit["summary"]
    print("=== Topic Mapping Consistency ===")
    print(f"记录 {s['total']} ｜ placeholder {s['placeholder_no_text']} ｜ "
          f"backfill_gap {s['backfill_gap']} ｜ extractor_window_gap "
          f"{s['extractor_window_gap']} ｜ aggregation_gap "
          f"{s['aggregation_gap']} ｜ strong_no_topic {s['strong_no_topic']}")
    print("全文口径主题分布:", json.dumps(
        s["topics_full_distribution"], ensure_ascii=False))
    for jid, v in per_j_out.items():
        if v["delta"]:
            print(f"  {jid:7s} delta(全文-存库): {v['delta']}")
    print(f"→ 已写 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
