# -*- coding: utf-8 -*-
"""audit_fr_cfr_links.py —— Phase 4B-1 Step 3：FR → codified_in → CFR 关系审计。

关系证据：FR API 官方字段 cfr_references（不得由标题猜测）
核验端：eCFR 官方 XML（outputs/cache/ecfr/title-*-part-*.xml）

产物：outputs/audit/fr_cfr_links.json
用法：py scripts/audit_fr_cfr_links.py [--json]
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

from app.policy.backfill import load_jsonl  # noqa: E402
from app.policy.cfr import build_fr_cfr_links, link_coverage  # noqa: E402

FR_OVERLAY = ROOT / "outputs" / "fr_identity_overlay.jsonl"
ECFR_CACHE = ROOT / "outputs" / "cache" / "ecfr"
OUT = ROOT / "outputs" / "audit" / "fr_cfr_links.json"


def ecfr_index() -> set[str]:
    keys: set[str] = set()
    for fp in glob.glob(str(ECFR_CACHE / "title-*-part-*.xml")):
        name = Path(fp).name                      # title-40-part-273.xml
        parts = name.replace(".xml", "").split("-")
        try:
            keys.add(f"CFR:{int(parts[1])}:{parts[3]}")
        except (IndexError, ValueError):
            continue
    return keys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    overlay = load_jsonl(FR_OVERLAY)
    links = build_fr_cfr_links(overlay)
    index = ecfr_index()
    cov = link_coverage(links, index)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fr_documents": len(overlay),
        "ecfr_verified_parts": sorted(index),
        **cov,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("=== FR → CFR 链接审计 ===")
    print(f"FR 文档 {len(overlay)} 条 → 链接 {cov['links_total']} 条 ｜ "
          f"唯一 CFR part {cov['unique_cfr_parts']} 个")
    print(f"eCFR 侧已核验 part：{sorted(index)}")
    print(f"命中率 {cov['matched_links']}/{cov['links_total']}"
          f" ({cov['matched_pct']}%)")
    if cov["unmatched_parts"]:
        print(f"未核验 part（Step 3 未采集，非失败）：{cov['unmatched_parts'][:20]}")
    for ex in cov["examples"][:8]:
        print(f"  · {ex['from']} ({ex['citation']}) → {ex['cfr_key']}")
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
