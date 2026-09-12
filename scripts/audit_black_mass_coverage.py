# -*- coding: utf-8 -*-
"""audit_black_mass_coverage.py —— Phase 4B-1 Step 10 §14：黑粉六线覆盖矩阵。

产物：outputs/audit/black_mass_coverage.json（全球 + EU + US 三视图）
用法：py scripts/audit_black_mass_coverage.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.backfill import load_records  # noqa: E402
from app.policy.black_mass import build_coverage  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "black_mass_coverage.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    records = load_records(ROOT)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records_total": len(records),
        "global": build_coverage(records),
        "EU": build_coverage(records, region="EU"),
        "US": build_coverage(records, region="US"),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("=== Black Mass 六线覆盖矩阵 ===")
    for view in ("global", "EU", "US"):
        s = payload[view]["summary"]
        print(f"\n[{view}] COVERED {s['covered']} / PARTIAL {s['partial']} / "
              f"MISSING {s['missing']} / BLOCKED {s['blocked']}")
        for line in payload[view]["lines"]:
            mark = {"COVERED": "✅", "PARTIAL": "⚠️", "MISSING": "❌",
                    "BLOCKED": "⛔"}[line["status"]]
            ev = line["best_evidence"][0]["evidence_id"] if line["best_evidence"] else "-"
            print(f"  {mark} {line['line_id']:14s} docs={line['documents']:4d} "
                  f"strong={line['strong_documents']:3d} best={ev} "
                  f"{('｜' + line['gap']) if line['gap'] else ''}")
    print(f"\n→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
