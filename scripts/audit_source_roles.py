# -*- coding: utf-8 -*-
"""audit_source_roles.py —— Phase 4B-1 Step 1：Source Role Gap Matrix。

产物：
    outputs/audit/source_role_gap_matrix.json
    outputs/audit/source_role_gap_matrix.csv

列（规格 §3）：
    jurisdiction, source_role, mandatory, critical, source_name, official_domain,
    configured, reachable, collector_available, enumeration_available,
    fulltext_available, metadata_available, last_checked, status,
    block_reason, evidence_count
    （另附 scope / declared_status / usable_endpoints / blocked_endpoints）

纪律：
    · 状态不得人工猜：由 registry + 真实 probe 结果 + 采集器 + 数据反推得出
    · 单端点失败不得把角色判死（source_access.derive_role_status）
    · URL 存在 ≠ COMPLETE

用法：
    py scripts/audit_source_roles.py
    py scripts/audit_source_roles.py --json
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

from app.policy.config import load_aliases, load_endpoints, load_registry  # noqa: E402
from app.policy.source_access import derive_role_status, expand_role_sources  # noqa: E402
from app.policy.source_universe import evidence_counts, has_collector  # noqa: E402

AUDIT = ROOT / "outputs" / "audit"
PROBE_FILE = AUDIT / "source_probe_results.json"
JSON_OUT = AUDIT / "source_role_gap_matrix.json"
CSV_OUT = AUDIT / "source_role_gap_matrix.csv"

COVERED = ("CONNECTED", "COMPLETE")

#: 不属于 supra/federal 分母的角色（归 EU_MEMBER_STATES / US_STATES scope）
_SUB_NATIONAL_ROLES = {
    "MEMBER_STATE_LEGISLATION", "MEMBER_STATE_OFFICIAL_GAZETTE",
    "MEMBER_STATE_CORE",
    "STATE_LEGISLATION", "STATE_ADMIN_RULES", "STATE_ENVIRONMENT_AGENCY",
    "STATE_EPR_PROGRAM", "STATE_CORE",
}


def _is_national_role(role: str) -> bool:
    return role in _SUB_NATIONAL_ROLES

#: 管辖区 → scope_level（饱和评价口径，规格 §13）
SCOPE_OF = {
    "EU": "EU_SUPRANATIONAL",
    "EU_27": "EU_MEMBER_STATES",
    "US": "US_FEDERAL",
    "US_STATES": "US_STATES",
}

COLUMNS = [
    "jurisdiction", "scope", "source_role", "mandatory", "critical",
    "source_name", "official_domain", "configured", "reachable",
    "collector_available", "enumeration_available", "fulltext_available",
    "metadata_available", "last_checked", "status", "block_reason",
    "evidence_count", "evidence_sources", "declared_status",
    "usable_endpoints", "blocked_endpoints",
]


def _load_probe() -> tuple[dict[tuple[str, str], dict], dict[str, list[dict]], str]:
    """→ (by (role,endpoint), by role, 说明文字)"""
    if not PROBE_FILE.exists():
        return {}, {}, "（无探测结果文件：状态为 UNVERIFIED 兜底）"
    data = json.loads(PROBE_FILE.read_text(encoding="utf-8"))
    by_ep: dict[tuple[str, str], dict] = {}
    by_role: dict[str, list[dict]] = {}
    for r in data:
        key = (r.get("source_role", ""), r.get("endpoint_id", ""))
        by_ep[key] = r
        by_role.setdefault(r.get("source_role", ""), []).append(r)
    return by_ep, by_role, ""


def build_rows() -> tuple[list[dict], dict]:
    registry = load_registry()
    endpoint_cfg = load_endpoints()
    eps_by_role = endpoint_cfg.by_role()
    _, probe_by_role, probe_note = _load_probe()
    ev = evidence_counts()
    known = sorted(ev.keys())
    alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
    rows: list[dict] = []

    for j in registry.jurisdictions:
        scope = SCOPE_OF.get(j.code, j.code)
        # --- 规范角色（EU/US 主体）---
        for role in j.source_roles:
            rc = eps_by_role.get(role.role)
            probe_rows = probe_by_role.get(role.role, [])
            sources = list(role.sources)
            # ★ 别名对账（Step 2）：逻辑源名 → 真实 source_id
            resolved = expand_role_sources(sources, alias_map, known)
            configured = bool(resolved)
            collector = any(has_collector(s) for s in resolved)
            evidence = sum(ev.get(s, 0) for s in resolved)
            evidence_sources = ";".join(f"{s}:{ev[s]}" for s in resolved if ev.get(s))
            st = derive_role_status(
                declared_status=role.status, sources_configured=configured,
                has_collector=collector, evidence_count=evidence,
                endpoint_results=probe_rows,
                status_ceiling=(rc.status_ceiling if rc else ""),
                gap_reason=role.gap_reason,
            )
            domain = (rc.official_domain if rc and rc.official_domain else
                      (rc.endpoints[0].official_domain if rc and rc.endpoints else ""))
            rows.append({
                "jurisdiction": j.code, "scope": scope, "source_role": role.role,
                "mandatory": role.expected, "critical": role.critical,
                "source_name": rc.source_name if rc else role.note[:60],
                "official_domain": domain or role.note[:60],
                "configured": configured, "reachable": st.reachable,
                "collector_available": collector,
                "enumeration_available": st.enumeration_available,
                "fulltext_available": st.fulltext_available,
                "metadata_available": st.metadata_available,
                "last_checked": st.last_checked, "status": st.status,
                "block_reason": st.block_reason,
                "evidence_count": evidence, "evidence_sources": evidence_sources,
                "declared_status": role.status,
                "usable_endpoints": ";".join(st.usable_endpoints),
                "blocked_endpoints": ";".join(st.blocked_endpoints),
            })
        # --- 成员国 / 州级行 ---
        for entry in (j.countries + j.states):
            cc = entry.get("code", "")
            srcs = list(entry.get("sources", []))
            collector = any(has_collector(s) for s in srcs)
            evidence = sum(ev.get(s, 0) for s in srcs)
            st = derive_role_status(
                declared_status=entry.get("status", "NOT_ONBOARDED"),
                sources_configured=bool(srcs), has_collector=collector,
                evidence_count=evidence, endpoint_results=None,
                gap_reason=entry.get("note", ""),
            )
            rows.append({
                "jurisdiction": cc, "scope": scope,
                "source_role": ("MEMBER_STATE_CORE" if j.code == "EU_27"
                                else "STATE_CORE"),
                "mandatory": True, "critical": False,
                "source_name": entry.get("name", ""),
                "official_domain": "", "configured": bool(srcs),
                "reachable": st.reachable, "collector_available": collector,
                "enumeration_available": False, "fulltext_available": False,
                "metadata_available": False, "last_checked": "",
                "status": st.status, "block_reason": st.block_reason,
                "evidence_count": evidence,
                "evidence_sources": ";".join(f"{s}:{ev[s]}" for s in srcs if ev.get(s)),
                "declared_status": entry.get("status", "NOT_ONBOARDED"),
                "usable_endpoints": "", "blocked_endpoints": "",
            })

    summary = _summarise(rows, probe_by_role, probe_note)
    return rows, summary


def _pct(part: int, total: int) -> float:
    return round(100.0 * part / total, 1) if total else 0.0


def _summarise(rows: list[dict], probe_by_role: dict, probe_note: str) -> dict:
    def cov(pred) -> dict:
        rs = [r for r in rows if pred(r)]
        covered = sum(1 for r in rs if r["status"] in COVERED)
        return {"total": len(rs), "covered": covered, "pct": _pct(covered, len(rs))}

    critical_blocked = [r for r in rows if r["critical"] and r["status"] == "BLOCKED"]
    blocked_eps = [
        {"role": role, "endpoint": e.get("endpoint_id"),
         "failure_type": e.get("failure_type"),
         "detail": str(e.get("failure_detail", ""))[:200]}
        for role, eps in sorted(probe_by_role.items())
        for e in eps if e.get("endpoint_status") == "BLOCKED"
    ]
    partial_caps = [
        {"role": role, "endpoint": e.get("endpoint_id"),
         "failure_type": e.get("failure_type")}
        for role, eps in sorted(probe_by_role.items())
        for e in eps if e.get("endpoint_status") == "PARTIAL"
    ]
    return {
        "probe_note": probe_note,
        "total_rows": len(rows),
        "EU_SUPRANATIONAL": {
            "mandatory": cov(lambda r: r["scope"] == "EU_SUPRANATIONAL"
                             and r["mandatory"] and not _is_national_role(r["source_role"])),
            "critical": cov(lambda r: r["scope"] == "EU_SUPRANATIONAL"
                            and r["critical"]),
        },
        "US_FEDERAL": {
            "mandatory": cov(lambda r: r["scope"] == "US_FEDERAL"
                             and r["mandatory"] and not _is_national_role(r["source_role"])),
            "critical": cov(lambda r: r["scope"] == "US_FEDERAL" and r["critical"]),
        },
        "EU_MEMBER_STATES": cov(lambda r: r["scope"] == "EU_MEMBER_STATES"),
        "US_STATES": cov(lambda r: r["scope"] == "US_STATES"),
        "critical_blocked_roles": [r["source_role"] for r in critical_blocked],
        "blocked_endpoints": blocked_eps,
        "partial_endpoints": partial_caps,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows, summary = build_rows()
    AUDIT.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "probe_file": str(PROBE_FILE.relative_to(ROOT)) if PROBE_FILE.exists() else "",
        "summary": summary,
        "rows": rows,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    with CSV_OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    s = summary
    print("=== Source Role Gap Matrix（Phase 4B-1）===")
    print(f"行数 {s['total_rows']}")
    if s["probe_note"]:
        print(f"⚠️ {s['probe_note']}")
    print(f"EU_SUPRANATIONAL  角色 mandatory {s['EU_SUPRANATIONAL']['mandatory']['covered']}"
          f"/{s['EU_SUPRANATIONAL']['mandatory']['total']}"
          f" ({s['EU_SUPRANATIONAL']['mandatory']['pct']}%) ｜ "
          f"critical {s['EU_SUPRANATIONAL']['critical']['covered']}"
          f"/{s['EU_SUPRANATIONAL']['critical']['total']}"
          f" ({s['EU_SUPRANATIONAL']['critical']['pct']}%)")
    print(f"US_FEDERAL        角色 mandatory {s['US_FEDERAL']['mandatory']['covered']}"
          f"/{s['US_FEDERAL']['mandatory']['total']}"
          f" ({s['US_FEDERAL']['mandatory']['pct']}%) ｜ "
          f"critical {s['US_FEDERAL']['critical']['covered']}"
          f"/{s['US_FEDERAL']['critical']['total']}"
          f" ({s['US_FEDERAL']['critical']['pct']}%)")
    print(f"EU_MEMBER_STATES  行 {s['EU_MEMBER_STATES']['covered']}"
          f"/{s['EU_MEMBER_STATES']['total']} ({s['EU_MEMBER_STATES']['pct']}%)")
    print(f"US_STATES         行 {s['US_STATES']['covered']}"
          f"/{s['US_STATES']['total']} ({s['US_STATES']['pct']}%)")
    print("-" * 118)
    print(f"{'SCOPE':17s} {'ROLE':36s} {'STATUS':9s} {'CRIT':4s} {'REACH':4s} "
          f"{'EVID':>5s}  BLOCK/REASON")
    print("-" * 118)
    for r in rows:
        if r["scope"] in ("EU_SUPRANATIONAL", "US_FEDERAL"):
            print(f"{r['scope'][:17]:17s} {r['source_role'][:36]:36s} "
                  f"{r['status']:9s} {'★' if r['critical'] else ' ' :4s} "
                  f"{r['reachable'][:4]:4s} {r['evidence_count']:>5d}  "
                  f"{r['block_reason'][:60]}")
    print("-" * 118)
    if s["blocked_endpoints"]:
        print("blocked endpoints（端点级失败，不代表角色整体判死）：")
        for e in s["blocked_endpoints"]:
            print(f"  · {e['role']}/{e['endpoint']}: {e['failure_type']}")
    print(f"→ 已写 {JSON_OUT.name} / {CSV_OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
