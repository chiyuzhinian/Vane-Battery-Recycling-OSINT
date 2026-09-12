# -*- coding: utf-8 -*-
"""audit_jurisdiction_priority.py —— Step 3：优先度评分 + Pilot 锁定。

产物：
    outputs/audit/jurisdiction_priority.csv   （全量 27 国 + 51 州 × 8 维分数）
    outputs/audit/jurisdiction_priority.json  （含 pilot/reserve 选择与依据）

用法：
    py scripts/audit_jurisdiction_priority.py            # 用最近一次 probe 结果
    py scripts/audit_jurisdiction_priority.py --probe    # 先跑第二轮带重试探测
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

from app.policy.jurisdiction_priority import (  # noqa: E402
    WEIGHTS, build_scores, load_signals, select_pilots,
)

AUDIT = ROOT / "outputs" / "audit"
PROBE_R2 = AUDIT / "jurisdiction_pilot_probe_r2.json"
PROBE_R1 = AUDIT / "jurisdiction_pilot_probe.json"
CSV_OUT = AUDIT / "jurisdiction_priority.csv"
JSON_OUT = AUDIT / "jurisdiction_priority.json"


def _load_probe() -> tuple[list[dict], str]:
    for fp, tag in ((PROBE_R2, "r2(带重试)"), (PROBE_R1, "r1(Plan Mode 预探测)")):
        if fp.exists():
            data = json.loads(fp.read_text(encoding="utf-8"))
            rows = data["rows"] if isinstance(data, dict) else data
            if any("probe_class" not in r for r in rows):
                for r in rows:                      # r1 无 probe_class → 本地归类
                    status = r.get("status")
                    if status is None:
                        r["probe_class"] = "error"
                    elif status == 200:
                        r["probe_class"] = ("http_200_spa" if r.get("spa_suspect")
                                            else "http_200")
                    elif 400 <= status < 500:
                        r["probe_class"] = "http_4xx"
                    elif 500 <= status < 600:
                        r["probe_class"] = "http_5xx"
                    else:
                        r["probe_class"] = "unknown"
            return rows, tag
    return [], "无（accessibility=unknown 兜底）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="先执行第二轮带重试探测")
    args = ap.parse_args()

    if args.probe:
        import asyncio
        import subprocess
        rc = subprocess.call([sys.executable, str(ROOT / "scripts"
                               / "probe_jurisdiction_candidates.py")])
        if rc != 0:
            print("⚠ 探测脚本非零退出，继续用已有产物")
        del asyncio

    probe_rows, probe_tag = _load_probe()
    signals = load_signals()
    scores = build_scores(signals, probe_rows)
    pilots = select_pilots(scores)

    # ---- CSV（全量）----
    cols = ["jurisdiction_id", "group", "score", "accessibility", "policy_signal",
            "confidence"] + list(WEIGHTS) + ["note"]
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CSV_OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for group, rows in (("EU_MEMBER_STATES", scores["EU_MEMBER_STATES"]),
                            ("US_STATES", scores["US_STATES"])):
            for r in rows:
                w.writerow([r["jurisdiction_id"], group, r["score"],
                            r["accessibility"], r["policy_signal"],
                            r["confidence"],
                            *[r.get(k, "") for k in WEIGHTS], r["note"]])

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "probe_source": probe_tag,
        "weights": WEIGHTS,
        "pilots": pilots,
        "scores": {k: scores[k] for k in ("EU_MEMBER_STATES", "US_STATES")},
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    print(f"=== Jurisdiction Priority（probe: {probe_tag}）===")
    for group in ("EU_MEMBER_STATES", "US_STATES"):
        print(f"[{group}] top 10：")
        for r in scores[group][:10]:
            print(f"   {r['jurisdiction_id']:8s} score={r['score']:.3f} "
                  f"access={r['accessibility']} policy={r['policy_signal']}")
    print("\n=== Pilot 锁定 ===")
    for k in ("EU_new_pilots", "EU_stretch_pilots", "US_state_pilots"):
        ids = [p["jurisdiction_id"] for p in pilots[k]]
        print(f"  {k}: {ids}")
    print("  EU_reserve:", [p["jurisdiction_id"] for p in pilots["EU_reserve"]])
    print("  US_reserve:", [p["jurisdiction_id"] for p in pilots["US_reserve"]])
    print(f"\n→ {CSV_OUT.relative_to(ROOT)} ｜ {JSON_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
