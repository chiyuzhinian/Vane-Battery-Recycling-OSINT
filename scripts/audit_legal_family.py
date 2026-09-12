# -*- coding: utf-8 -*-
"""audit_legal_family.py —— 法律家族完整性审计（Phase 4A §15）。

用法：
    py scripts/audit_legal_family.py --region EU
    py scripts/audit_legal_family.py --region US --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.legal_graph import build_family_status, write_family_audit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--region", default="EU")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    statuses = build_family_status()
    path = write_family_audit()
    if args.json:
        print(json.dumps([s.__dict__ for s in statuses],
                         ensure_ascii=False, indent=2))
        return 0

    print(f"=== 法律家族审计（写至 {path.relative_to(ROOT)}）===")
    for s in statuses:
        mark = "✅" if not s.unresolved_relations else "⚠️"
        print(f"\n{mark} {s.root_act}（{s.root_name}）")
        print(f"   家族成员 {s.members_total} 条（其中国家转化 {s.national_transpositions}）")
        print(f"   期望关系: {', '.join(s.expected_relation_types)}")
        for rel, members in sorted(s.found_relations.items()):
            print(f"   ├─ {rel:18s} {len(members)} 条  例: {members[0][:44]}")
        if s.unresolved_relations:
            print(f"   └─ 未解决: {', '.join(s.unresolved_relations)}")
        print(f"   完整性 family_completeness={s.family_completeness}")
    unresolved = sum(len(s.unresolved_relations) for s in statuses)
    print(f"\nP0 家族未解决关系总数: {unresolved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
