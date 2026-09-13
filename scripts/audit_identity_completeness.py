# -*- coding: utf-8 -*-
"""audit_identity_completeness.py —— Step 2：身份完整度 before/after 分解。

产物：outputs/audit/identity_completeness.json

口径（规格 §七）：
    核心 5 字段 = canonical_id / official_identifier / issuer / language /
    official_url；分母 = **专线 corpus**（discovery-layer 单列，不计分母）；
    分解 = new（轮次采集）vs historical（专线旧记录）vs discovery_excluded。

用法：py scripts/audit_identity_completeness.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import load_jsonl, load_records  # noqa: E402
from app.policy.identity_hardening import (  # noqa: E402
    CORE_FIELDS, decompose_identity, identity_v2_completeness,
)
from app.policy.identity_jurisdiction import (  # noqa: E402
    identity_from_meta, is_dedicated_source,
)
from app.policy.jurisdiction_map import jurisdiction_of  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "identity_completeness.json"
OVERLAY = ROOT / "outputs" / "policy_metadata_overlay.jsonl"
TARGETS = ("SE", "FI", "US-CA", "US-WA", "DE", "NL", "ES", "FR")


def before_pct(records: list[dict], jid: str) -> float:
    """修复前口径：既有 identity 字段或 meta.doc_key 路径 + URL 补充
    （**不做 v2 编号构造**——即 2B0 之前系统能拿到的身份）。"""
    total = full = 0
    for r in records:
        if not is_dedicated_source(str(r.get("source_id") or "")):
            continue
        if jurisdiction_of(r) != jid:
            continue
        total += 1
        ident = dict(r.get("identity") or identity_from_meta(r.get("meta")) or {})
        if not ident.get("official_url"):
            ident["official_url"] = ((r.get("meta") or {}).get("official_url")
                                     or r.get("url") or "")
        if all(ident.get(f) for f in CORE_FIELDS):
            full += 1
    return round(100.0 * full / total, 1) if total else 0.0


def main() -> int:
    records = load_records(ROOT)
    overlay = load_jsonl(OVERLAY) if OVERLAY.exists() else {}
    result: dict = {"generated_at": datetime.now(timezone.utc).isoformat(
        timespec="seconds"),
        "core_fields": list(CORE_FIELDS),
        "note": ("complete = 核心 5 字段全有；v2 构造仅来自官方编号 meta，"
                 "无编号即如实缺（禁止默认值）"),
        "jurisdictions": {}}
    for jid in TARGETS:
        before = before_pct(records, jid)
        after = identity_v2_completeness(records, jid, overlay)
        dec = decompose_identity(records, jid, overlay)
        result["jurisdictions"][jid] = {
            "before_pct": before, "after": after, "decomposition": dec,
        }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    print("=== Identity Completeness (core 5 fields, dedicated corpus) ===")
    for jid, e in result["jurisdictions"].items():
        d = e["decomposition"]
        print(f"  {jid:6s} before {e['before_pct']:5.1f}% → after "
              f"{e['after']['pct']:5.1f}% ({e['after']['complete']}/"
              f"{e['after']['total']}) | new {d['new']['complete']}/"
              f"{d['new']['total']} ({d['new']['pct']}) | hist "
              f"{d['historical']['complete']}/{d['historical']['total']} "
              f"({d['historical']['pct']}) | excl {d['discovery_layer_excluded']}")
        for m in (d["new"]["missing"] + d["historical"]["missing"])[:3]:
            print(f"        missing: {m['evidence_id']} lacks={m['lacks']}")
    print(f"→ 已写 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
