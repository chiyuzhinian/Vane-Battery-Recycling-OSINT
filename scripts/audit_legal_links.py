# -*- coding: utf-8 -*-
"""audit_legal_links.py —— Phase 4B-1 Step 4：US 法律关系总审计。

三类关系（全部官方证据）：
    FR → codified_in      → CFR  （FR API cfr_references）
    CFR → AUTHORIZED_BY   → USC  （eCFR <AUTH> 权威注记）
    PL  → AMENDS/CODIFIED_AS → USC（PL 官方文本 / govinfo NOTE 注记）

产物：outputs/audit/us_legal_links.json
用法：py scripts/audit_legal_links.py [--json]
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
from app.policy.us_code import build_cfr_usc_links  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "us_legal_links.json"
FR_OVERLAY = ROOT / "outputs" / "fr_identity_overlay.jsonl"
ECFR_CACHE = ROOT / "outputs" / "cache" / "ecfr"


def _load_jsonl_files(pattern: str) -> list[dict]:
    rows: dict[str, dict] = {}
    for fp in sorted(glob.glob(str(ROOT / "outputs" / pattern))):
        for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("evidence_id"):
                rows[r["evidence_id"]] = r
    return list(rows.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    fr_links = build_fr_cfr_links(load_jsonl(FR_OVERLAY))
    ecfr_index = set()
    for fp in glob.glob(str(ECFR_CACHE / "title-*-part-*.xml")):
        parts = Path(fp).name.replace(".xml", "").split("-")
        try:
            ecfr_index.add(f"CFR:{int(parts[1])}:{parts[3]}")
        except (IndexError, ValueError):
            continue

    ecfr_records = _load_jsonl_files("ecfr_*.jsonl")
    cfr_usc = build_cfr_usc_links(ecfr_records)

    pl_usc: list[dict] = []
    for rec in _load_jsonl_files("uscplaw_*.jsonl"):
        meta = rec.get("meta") or {}
        if meta.get("pl_key"):
            pl_usc += list(meta.get("relations") or [])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fr_cfr": link_coverage(fr_links, ecfr_index),
        "cfr_usc": {
            "links_total": len(cfr_usc),
            "unique_targets": len({l["to_key"] for l in cfr_usc}),
            "examples": cfr_usc[:10],
        },
        "pl_usc": {
            "links_total": len(pl_usc),
            "unique_targets": len({l["to_key"] for l in pl_usc}),
            "by_relation": {
                rel: sum(1 for l in pl_usc if l["relation"] == rel)
                for rel in sorted({l["relation"] for l in pl_usc})
            },
            "examples": pl_usc[:10],
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("=== US 法律关系审计 ===")
    fc = payload["fr_cfr"]
    print(f"FR → CFR :  链接 {fc['links_total']} ｜ 核验 {fc['matched_links']}"
          f" ({fc['matched_pct']}%) ｜ 唯一 part {fc['unique_cfr_parts']}")
    cu = payload["cfr_usc"]
    print(f"CFR → USC:  链接 {cu['links_total']} ｜ 唯一 USC 目标 {cu['unique_targets']}")
    pu = payload["pl_usc"]
    print(f"PL → USC :  链接 {pu['links_total']} ｜ 唯一目标 {pu['unique_targets']}"
          f" ｜ {pu['by_relation']}")
    for ex in cu["examples"][:5]:
        print(f"  · {ex['from_key']} → {ex['to_key']}（{ex['relation']}）")
    for ex in pu["examples"][:5]:
        print(f"  · {ex['from_key']} → {ex['to_key']}（{ex['relation']}）")
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
