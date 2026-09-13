# -*- coding: utf-8 -*-
"""audit_jurisdiction_coverage.py —— Step 7：管辖地覆盖矩阵（含主题/黑粉）。

产物：
    outputs/audit/jurisdiction_coverage.json
    outputs/audit/jurisdiction_coverage.csv

纪律：条数为描述性统计；覆盖分母=契约 mandatory 角色；主题=五态矩阵。

用法：py scripts/audit_jurisdiction_coverage.py [--json]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import load_records  # noqa: E402
from app.policy.jurisdiction_coverage import (  # noqa: E402
    build_jurisdiction_coverage,
)

JSON_OUT = ROOT / "outputs" / "audit" / "jurisdiction_coverage.json"
CSV_OUT = ROOT / "outputs" / "audit" / "jurisdiction_coverage.csv"

CSV_COLS = ["jurisdiction", "level", "records", "sources_covered",
            "sources_mandatory", "identity_pct", "A1", "A2", "B", "C", "D",
            "topics_covered", "topics_partial", "black_mass_covered",
            "failures", "proof_sources"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    records = load_records(ROOT)
    coverage = build_jurisdiction_coverage(records)
    coverage["generated_at"] = datetime.now(timezone.utc).isoformat(
        timespec="seconds")
    coverage["records_total"] = len(records)
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(coverage, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    with CSV_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLS)
        for jid, row in sorted(coverage["jurisdictions"].items()):
            acc = row["acceptance"]
            topics = row["topics"]
            w.writerow([
                jid, row["level"], row["records"],
                (row["sources"] or {}).get("covered", ""),
                (row["sources"] or {}).get("mandatory", ""),
                row["identity"]["pct"],
                acc.get("A1", 0), acc.get("A2", 0), acc.get("B", 0),
                acc.get("C", 0), acc.get("D", 0),
                sum(1 for v in topics.values() if v == "COVERED"),
                sum(1 for v in topics.values() if v == "PARTIAL"),
                row["black_mass"]["covered"], len(row["failures"]),
                (row["proof"] or {}).get("sources", ""),
            ])

    if args.json:
        print(json.dumps(coverage, ensure_ascii=False, indent=2)[:6000])
        return 0

    s = coverage["summary"]
    print("=== Jurisdiction Coverage ===")
    print(f"管辖地 {s['total']} ｜ ACTIVE {s['active']} ｜ COLLECTED "
          f"{s['collected']} ｜ BLOCKED {s['blocked']} ｜ REFERENCE "
          f"{s['reference']} ｜ 主题覆盖格 {s['topics_covered_cells']}")
    print(f"{'jid':<8s} {'level':<12s} {'rec':>4s} {'src':>5s} {'id%':>5s} "
          f"{'A/B':>5s} {'topic(C/P)':>10s} {'bm':>3s} {'fail':>4s}")
    for jid, row in sorted(coverage["jurisdictions"].items()):
        if row["level"] in ("NOT_ONBOARDED",) and not row["records"]:
            continue
        topics = row["topics"]
        tc = sum(1 for v in topics.values() if v == "COVERED")
        tp = sum(1 for v in topics.values() if v == "PARTIAL")
        ab = row["acceptance"].get("A1", 0) + row["acceptance"].get("A2", 0) \
            + row["acceptance"].get("B", 0)
        src = row["sources"] or {}
        print(f"{jid:<8s} {row['level']:<12s} {row['records']:>4d} "
              f"{str(src.get('covered', '-')) + '/' + str(src.get('mandatory', '-')):>5s} "
              f"{row['identity']['pct']:>5.1f} {ab:>5d} "
              f"{str(tc) + '/' + str(tp):>10s} {row['black_mass']['covered']:>3d} "
              f"{len(row['failures']):>4d}")
    print(f"\n→ {JSON_OUT.relative_to(ROOT)} ｜ {CSV_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
