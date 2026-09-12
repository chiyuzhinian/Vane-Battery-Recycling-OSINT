# -*- coding: utf-8 -*-
"""backfill_policy_metadata.py —— Phase 4B-1 Step 2 升级版（薄封装 app.policy.backfill）。

设计（规格 §12 + §14）：
    · 不修改 outputs/*.jsonl（不可变快照）→ 写叠加层 outputs/policy_metadata_overlay.jsonl
    · 默认 --dry-run；--apply 才落盘；落盘为**增量合并**（保留旧行）
    · 若存在 outputs/fr_identity_overlay.jsonl（enrich_us_identity.py 产物），
      自动并入 legal_identity（canonical_id/official_identifier/issuer/status）
      并附加 identity_us 块（RIN / cfr_references / citation / action …）

用法：
    py scripts/backfill_policy_metadata.py                        # 全部 dry-run
    py scripts/backfill_policy_metadata.py --region US --only-missing --limit 100
    py scripts/backfill_policy_metadata.py --region US --source-role FEDERAL_REGISTER
    py scripts/backfill_policy_metadata.py --apply --region EU
    py scripts/backfill_policy_metadata.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import (  # noqa: E402
    backfill_report, build_overlay_row, filter_records, load_jsonl,
    load_records, merge_rows_into_overlay, record_completeness, write_overlay,
)
from app.policy.config import load_aliases  # noqa: E402
from app.policy.source_universe import evidence_counts  # noqa: E402

OUT = ROOT / "outputs"
OVERLAY = OUT / "policy_metadata_overlay.jsonl"
FR_OVERLAY = OUT / "fr_identity_overlay.jsonl"


def _fr_identity_map() -> dict[str, dict]:
    rows = load_jsonl(FR_OVERLAY)
    return {eid: row["fr_identity"] for eid, row in rows.items()
            if row.get("fr_identity")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写 overlay（默认 dry-run）")
    ap.add_argument("--only", default="", help="只处理 evidence_id 前缀匹配的记录")
    ap.add_argument("--region", default="", help="US / EU / 空=全部")
    ap.add_argument("--source-role", default="", help="按角色过滤（经别名展开）")
    ap.add_argument("--only-missing", action="store_true",
                    help="只处理身份不完整（missing_fields>2）的记录")
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 条")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    records = load_records(ROOT)
    alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
    known = sorted(evidence_counts().keys())
    selected = filter_records(records, region=args.region,
                              source_role=args.source_role,
                              only_missing=args.only_missing,
                              limit=args.limit, alias_map=alias_map,
                              known_source_ids=known,
                              evidence_prefix=args.only)

    fr_map = _fr_identity_map()
    rows = [build_overlay_row(r, fr_identity=fr_map.get(r.get("evidence_id")))
            for r in selected]
    before = record_completeness(selected)
    after = record_completeness(selected, fr_identities=fr_map)

    # failed / ambiguous / human review（来自 FR 富化产物）
    fr_rows = load_jsonl(FR_OVERLAY)
    scoped = {r["evidence_id"] for r in selected}
    failed = sum(1 for eid in fr_rows if eid in scoped and not fr_rows[eid].get("fr_identity"))
    ambiguous = sum(1 for eid, row in fr_rows.items()
                    if eid in scoped and row.get("fr_ambiguous"))
    human_review = sum(1 for r in rows if r.get("acceptance_review"))
    report = backfill_report(before, after, failed=failed, ambiguous=ambiguous,
                             human_review_required=human_review)

    if args.json:
        print(json.dumps({"selected": len(selected), "region": args.region,
                          "source_role": args.source_role,
                          "report": report,
                          "acceptance_dist": dict(Counter(
                              r["acceptance_class"] for r in rows)),
                          "instrument_dist": dict(Counter(
                              r["instrument_type"] for r in rows).most_common(10))},
                         ensure_ascii=False, indent=2))
    else:
        print(f"记录 {len(selected)} 条（{'APPLY' if args.apply else 'DRY-RUN'}"
              f"；region={args.region or 'ALL'} role={args.source_role or 'ALL'}"
              f"{' only-missing' if args.only_missing else ''}）")
        print(f"分类分布: {dict(Counter(r['acceptance_class'] for r in rows))}")
        print(f"文书类型: {dict(Counter(r['instrument_type'] for r in rows).most_common(8))}")
        print(f"富化来源: fr_identity_overlay={len(fr_rows)} 行 ｜ 本次命中 {sum(1 for r in selected if r.get('evidence_id') in fr_map)}")
        print(f"身份完整度 before={before['complete']}/{before['total']} ({before['pct']}%)"
              f"  →  after={after['complete']}/{after['total']} ({after['pct']}%)"
              f"  Δ{report['delta_pct']}%")
        print(f"failed={failed} ambiguous={ambiguous} human_review_required={human_review}")

    if not args.apply:
        print("\n（dry-run —— 加 --apply 写 overlay；原始 evidence 不会被修改）")
        return 0

    merged = merge_rows_into_overlay(load_jsonl(OVERLAY), rows)
    write_overlay(OVERLAY, merged)
    print(f"\n→ 已写 {OVERLAY.name}（{len(merged)} 行；本次 +{len(rows)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
