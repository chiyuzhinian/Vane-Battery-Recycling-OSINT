# -*- coding: utf-8 -*-
"""probe_source_endpoints.py —— Phase 4B-1 Step 1：真实探测官方端点。

用法：
    py scripts/probe_source_endpoints.py                 # 全部端点（联网）
    py scripts/probe_source_endpoints.py --role OECD --role CBP
    py scripts/probe_source_endpoints.py --json          # 只输出 JSON 摘要
    py scripts/probe_source_endpoints.py --timeout 30

产物：outputs/audit/source_probe_results.json
纪律：失败分类（HTTP_403/TIMEOUT/…）与 NO_RESULTS 严格分离，见 app/policy/source_access.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.source_probe import probe_all  # noqa: E402

AUDIT = ROOT / "outputs" / "audit"
OUT_FILE = AUDIT / "source_probe_results.json"


async def run(args: argparse.Namespace) -> int:
    only = set(args.role) if args.role else None
    results = await probe_all(only_roles=only, default_timeout=args.timeout,
                              concurrency=args.concurrency)
    AUDIT.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    ok = sum(1 for r in results if r["endpoint_status"] == "ACCESSIBLE")
    part = sum(1 for r in results if r["endpoint_status"] == "PARTIAL")
    blocked = sum(1 for r in results if r["endpoint_status"] == "BLOCKED")
    if args.json:
        print(json.dumps({"file": str(OUT_FILE), "endpoints": len(results),
                          "accessible": ok, "partial": part, "blocked": blocked,
                          "results": results}, ensure_ascii=False, indent=2))
        return 0

    print(f"=== 端点探测：{len(results)} 个 ｜ ACCESSIBLE {ok} / PARTIAL {part} "
          f"/ BLOCKED {blocked} ===")
    print(f"{'ROLE':32s} {'ENDPOINT':28s} {'STATUS':9s} {'HTTP':5s} {'FAILURE':18s} {'ms':>6s}")
    print("-" * 108)
    for r in results:
        print(f"{r['source_role'][:32]:32s} {r['endpoint_id'][:28]:28s} "
              f"{r['endpoint_status']:9s} {str(r['http_status'] or '-'):5s} "
              f"{r['failure_type']:18s} {str(r['latency_ms'] or '-'):>6s}")
        if r["failure_type"] not in ("NONE", "NO_RESULTS") and r["failure_detail"]:
            print(f"    ↳ {r['failure_detail'][:150]}")
    print("-" * 108)
    print(f"→ 已写 {OUT_FILE}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", action="append", default=[],
                    help="只探测指定角色（可多次）")
    ap.add_argument("--timeout", type=float, default=25.0)
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
