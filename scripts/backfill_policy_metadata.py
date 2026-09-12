# -*- coding: utf-8 -*-
"""backfill_policy_metadata.py —— Phase 4A 新字段回填（兼容旧数据）。

设计（规格 §14：旧 evidence 不允许直接覆盖）：
    不修改 outputs/*.jsonl（不可变快照），而是写**叠加层**：
        outputs/policy_metadata_overlay.jsonl
        {evidence_id, acceptance_class, relevant, confidence, topic_ids,
         reasons, evidence_quotes, instrument_type, binding_force,
         legal_identity: {...}, backfilled_at, backfill_version}
    消费方（audit CLI / 未来 store）自行 merge。

用法：
    py scripts/backfill_policy_metadata.py              # dry-run（默认）
    py scripts/backfill_policy_metadata.py --apply      # 写 overlay
    py scripts/backfill_policy_metadata.py --apply --only eu_  # 只回填 EU 记录
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.legal_identity import resolve_identity  # noqa: E402

OUT = ROOT / "outputs"
OVERLAY = OUT / "policy_metadata_overlay.jsonl"
BACKFILL_VERSION = "phase4a.v1"


def load_records() -> list[dict]:
    rows: dict[str, dict] = {}
    for fp in glob.glob(str(OUT / "*.jsonl")):
        name = Path(fp).name
        if name.startswith(("_", "review", "policy_metadata_overlay")):
            continue
        for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = r.get("evidence_id")
            if eid and eid not in rows:
                rows[eid] = r
    return list(rows.values())


def build_overlay_row(record: dict) -> dict:
    res = classify_record(record)
    idn = resolve_identity(record)
    return {
        "evidence_id": record.get("evidence_id"),
        "acceptance_class": res.classification,
        "acceptance_relevant": res.relevant,
        "acceptance_confidence": round(res.confidence, 3),
        "topic_ids": res.topic_ids,
        "acceptance_reasons": res.reason_codes,
        "evidence_quotes": res.evidence_quotes[:3],
        "acceptance_review": res.requires_human_review,
        "instrument_type": idn.instrument_type,
        "binding_force": idn.binding_force,
        "legal_status": idn.status,
        "legal_identity": {
            "canonical_id": idn.canonical_id,
            "jurisdiction": idn.jurisdiction,
            "issuer": idn.issuer,
            "official_identifier": idn.official_identifier,
            "language": idn.language,
            "missing_fields": idn.missing_fields,
        },
        "backfill_version": BACKFILL_VERSION,
        "backfilled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写 overlay（默认 dry-run）")
    ap.add_argument("--only", default="", help="只处理 evidence_id 前缀匹配的记录")
    args = ap.parse_args()

    records = load_records()
    if args.only:
        records = [r for r in records
                   if str(r.get("evidence_id") or "").startswith(args.only)]
    print(f"记录 {len(records)} 条（{'APPLY' if args.apply else 'DRY-RUN'}）")

    rows = [build_overlay_row(r) for r in records]
    from collections import Counter
    dist = Counter(r["acceptance_class"] for r in rows)
    inst = Counter(r["instrument_type"] for r in rows)
    print(f"分类分布: {dict(dist)}")
    print(f"文书类型: {dict(inst.most_common(8))}")

    if not args.apply:
        print("\n（dry-run —— 加 --apply 写 overlay；原始 evidence 不会被修改）")
        return 0

    # 合并写：保留 overlay 中不在本次处理范围的旧行（增量更新）
    keep: dict[str, dict] = {}
    if OVERLAY.exists():
        for line in OVERLAY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    old = json.loads(line)
                    keep[old["evidence_id"]] = old
                except json.JSONDecodeError:
                    pass
    for r in rows:
        keep[r["evidence_id"]] = r
    with OVERLAY.open("w", encoding="utf-8") as f:
        for r in keep.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n→ 已写 {OVERLAY.name}（{len(keep)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
