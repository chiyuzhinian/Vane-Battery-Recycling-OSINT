# -*- coding: utf-8 -*-
"""audit_domain_relevance.py —— Step 4：域相关性审计。

产物：outputs/audit/domain_relevance.json
内容：五级域分布 · 护栏改写（违规降级）清单 · 便携/消费电池不得 A1/A2 验证。

用法：py scripts/audit_domain_relevance.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import load_records  # noqa: E402
from app.policy.domain_scope import SCOPES, audit_domain_guard  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "domain_relevance.json"


def main() -> int:
    records = load_records(ROOT)
    audit = audit_domain_guard(records)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "scopes": list(SCOPES),
        "note": ("GENERAL_BATTERY_BACKGROUND 不得 A1/A2/B；OUT_OF_SCOPE 仅 D；"
                 "SUPPORTING 最高 B（guard_class 约束矩阵）"),
        **audit,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("=== Domain Relevance ===")
    for s in SCOPES:
        print(f"  {s:28s} {audit['distribution'].get(s, 0)}")
    print(f"护栏改写（降级）: {audit['violations_count']}")
    for v in audit["violations"][:10]:
        print(f"  [{v['jurisdiction']}] {v['class_before']}→{v['class_after']}"
              f" ({v['domain_scope']}) {v['evidence_id']} "
              f"| {v['title'][:50]}")
    print(f"→ 已写 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
