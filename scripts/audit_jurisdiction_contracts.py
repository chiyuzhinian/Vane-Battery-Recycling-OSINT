# -*- coding: utf-8 -*-
"""audit_jurisdiction_contracts.py —— Phase 4B-2A Step 2：契约注册表审计。

产物：outputs/audit/jurisdiction_contracts.json
（含每管辖地 mandatory 角色覆盖 + 通道/缺口说明 + 校验警告）

用法：py scripts/audit_jurisdiction_contracts.py [--json]
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

from app.policy.jurisdiction_onboarding import build_contract_registry  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "jurisdiction_contracts.json"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reg = build_contract_registry()
    reg["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(reg, ensure_ascii=False, indent=2))
        return 0

    print("=== Jurisdiction Onboarding 契约注册表 ===")
    for c in reg["contracts"]:
        print(f"[{c['jurisdiction_id']}] {c['name'].get('zh', '')} "
              f"level={c['level']} 语言={','.join(c['official_languages'])} ｜ "
              f"mandatory 覆盖 {c['covered_roles']}/{c['mandatory_roles']} "
              f"({c['coverage_pct']}%)")
        for r in c["roles"]:
            mark = "✅" if r["covered"] else "▫️"
            chans = ",".join(ch["source_id"] for ch in r["channels"]) or "—"
            gap = f" ｜ gap: {r['gap']}" if r["gap"] and not r["covered"] else ""
            print(f"   {mark} {r['role']:38s} {chans}{gap}")
    for e in reg["errors"]:
        print(f"   ❌ {e['jurisdiction_id']}: {e['error']}")
    print(f"\n→ 已写 {OUT.relative_to(ROOT)}")
    return 1 if reg["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
