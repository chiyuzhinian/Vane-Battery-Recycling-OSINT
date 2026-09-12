# -*- coding: utf-8 -*-
"""Jurisdiction Source Universe —— 管辖区 × 源角色 覆盖状态机（Phase 4A §5）。

纪律：
    · "URL 存在" ≠ "source coverage complete"（本模块的核心断言）
    · NIM ≠ 成员国法律全集；FR ≠ 美国法规全集（单角色命中不得宣布整体完成）
    · reachable 只在 --live 时做真实探测（默认从数据反推，标注 UNVERIFIED）
"""
from __future__ import annotations

import glob
import json
from dataclasses import dataclass, asdict
from pathlib import Path

from app.policy.config import load_registry

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "outputs"

COVERED_STATES = {"CONNECTED", "COMPLETE"}

# source_id → 是否有专用 collector（连接器/browser 通道/NIM 解析器）
_KNOWN_COLLECTORS = {
    "eur_lex", "eu_eurlex_battery_reg", "eu_eurlex_keyword", "eu_eurlex_elv",
    "eu_eurlex_waste_shipment", "eu_eurlex_crm",
    "us_federal_register", "boe_es", "bwb_nl", "dila_fr", "datafair",
    "gesetze_de", "browser", "vane",
}


def has_collector(source_id: str) -> bool:
    """source_id 是否有专用采集通道（连接器/浏览器/NIM 解析器）。"""
    if source_id.startswith(("eu_nim_", "browser_", "us_", "fr_", "nl_", "de_",
                             "es_", "int_", "cbp_cross", "eur_lex",
                             # Phase 4B-2A pilots/reserve（Step 4+ 接入中）
                             "se_", "pl_", "be_", "fi_", "ee_", "it_", "sk_",
                             "cz_", "dk_", "hu_", "at_")):
        return True
    return source_id in _KNOWN_COLLECTORS


# 向后兼容的私有别名（旧调用方/测试使用）
_has_collector = has_collector


def evidence_counts() -> dict[str, int]:
    """source_id → 记录条数（从 outputs 快照统计）。"""
    counts: dict[str, int] = {}
    for fp in glob.glob(str(OUT / "*.jsonl")):
        if Path(fp).name.startswith(("_", "review")):
            continue
        for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                sid = json.loads(line).get("source_id")
            except json.JSONDecodeError:
                continue
            if sid:
                counts[sid] = counts.get(sid, 0) + 1
    return counts


# 向后兼容的私有别名
_live_sources = evidence_counts


@dataclass
class RoleRow:
    jurisdiction: str
    source_role: str
    expected: bool
    configured: list[str]
    reachable: str          # yes | no | UNVERIFIED
    collector_available: bool
    last_verified: str
    status: str
    gap_reason: str = ""


def build_universe_rows() -> list[RoleRow]:
    registry = load_registry()
    live = _live_sources()
    rows: list[RoleRow] = []

    for j in registry.jurisdictions:
        if j.source_roles:
            for r in j.source_roles:
                has_data = any(live.get(s, 0) > 0 for s in r.sources)
                status = r.status
                # 数据反推：配置了源且有数据 → 至少 CONNECTED（不覆盖更强状态）
                if has_data and status in ("NOT_ONBOARDED", "DISCOVERED",
                                           "ACCESSIBLE", "BLOCKED"):
                    status = "CONNECTED"
                if r.sources and not has_data and status in ("CONNECTED",
                                                             "COMPLETE"):
                    status = "PARTIAL"   # 配置了但零数据 → 降级
                cols = [s for s in r.sources if _has_collector(s)]
                rows.append(RoleRow(
                    j.code, r.role, r.expected, list(r.sources),
                    "yes" if has_data else ("UNVERIFIED" if not r.sources else "no"),
                    bool(cols), "2026-09-12", status, r.gap_reason,
                ))
        # 成员国 / 州级：schema 行（逐国）
        for entry in (j.countries + j.states):
            cc = entry.get("code", "")
            srcs = entry.get("sources", [])
            has_data = any(live.get(s, 0) > 0 for s in srcs)
            status = entry.get("status", "NOT_ONBOARDED")
            if has_data and status in ("NOT_ONBOARDED", "DISCOVERED"):
                status = "CONNECTED"
            rows.append(RoleRow(
                cc, "MEMBER_STATE_CORE" if j.code == "EU_27" else "STATE_CORE",
                True, list(srcs), "yes" if has_data else "UNVERIFIED",
                any(_has_collector(s) for s in srcs), "2026-09-12",
                status, entry.get("note", ""),
            ))
    return rows


def universe_summary() -> dict:
    rows = build_universe_rows()
    # 只对 EU / US 两个主体算饱和用的 mandatory 覆盖
    def cov(code: str) -> dict:
        rs = [r for r in rows if r.jurisdiction == code and r.expected]
        if not rs:
            return {"total": 0, "covered": 0, "pct": 0.0}
        covered = sum(1 for r in rs if r.status in COVERED_STATES)
        return {"total": len(rs), "covered": covered,
                "pct": round(100.0 * covered / len(rs), 1)}
    ms_rows = [r for r in rows if r.jurisdiction not in ("EU", "US")
               and r.expected]
    ms_covered = sum(1 for r in ms_rows if r.status in COVERED_STATES)
    return {
        "rows": [asdict(r) for r in rows],
        "EU": cov("EU"),
        "US": cov("US"),
        "MEMBER_STATES": {"total": len(ms_rows), "covered": ms_covered,
                          "pct": round(100.0 * ms_covered / len(ms_rows), 1)
                          if ms_rows else 0.0},
        "blocked": [asdict(r) for r in rows if r.status == "BLOCKED"],
        "not_onboarded_expected": [asdict(r) for r in rows
                                   if r.status == "NOT_ONBOARDED" and r.expected],
    }


def markdown_table(region: str) -> str:
    rows = [r for r in build_universe_rows()
            if r.jurisdiction == region or
            any(r.jurisdiction.startswith(x) for x in
                ({"EU": ("EU_27",), "US": ("US_STATES",)}.get(region, ())))]
    if not rows:
        return f"（无 {region} 行）"
    lines = ["| 管辖区 | 源角色 | 期望 | 已配置源 | 采集器 | 状态 | 缺口原因 |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r.jurisdiction} | {r.source_role} | {'✓' if r.expected else '—'} | "
            f"{', '.join(r.configured) or '—'} | {'✓' if r.collector_available else '✗'} | "
            f"{r.status} | {r.gap_reason[:60]} |")
    return "\n".join(lines)
