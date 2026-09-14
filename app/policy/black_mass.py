# -*- coding: utf-8 -*-
"""Black Mass 六线覆盖矩阵（Phase 4B-1 Step 10 §14）—— 纯逻辑。

六条线（每条独立评估）：
    1 waste_status     废物定性
    2 hazardous        危废定性
    3 transport        运输（危货）
    4 transboundary    越境转移
    5 customs          海关/进出口
    6 end_of_waste     再生料/废物终结

状态：COVERED（有 A/B 级强证据）｜ PARTIAL（仅背景/弱证据）｜ MISSING（0 条）｜ BLOCKED（通道被阻）
"""
from __future__ import annotations

import re

LINES: list[tuple[str, str, str]] = [
    ("waste_status", "废物定性（是否废物）",
     r"waste\s+batter|batteries\s+and\s+waste|waste\s+electrical|end-of-life\s+vehicl"
     r"|universal\s+waste|废弃物|废电池"),
    ("hazardous", "危废定性",
     r"hazardous\s+waste|hazardous\s+materials?|dangerous\s+goods|identification\s+and\s+listing"
     r"|危险废物|危废"),
    ("transport", "运输（危货/包装）",
     r"transport|shipment|packaging|aircraft|\bADR\b|carriage\s+of\s+dangerous|"
     r"托运|运输"),
    ("transboundary", "越境转移",
     r"transboundary|shipments?\s+of\s+waste|waste\s+shipments?|2024/1157|green\s+control"
     r"|amber\s+control|越境"),
    ("customs", "海关/进出口/贸易救济",
     r"customs|tariff|imports?\b|exports?\b|countervailing|anti-dumping|foreign-trade\s+zone"
     r"|\bCROSS\b|\bruling\b|duty|关税|进出口"),
    ("end_of_waste", "再生料/废物终结/回收效率",
     r"end-of-waste|recycled\s+content|recycling\s+efficiency|recovery\s+operation"
     r"|secondary\s+material|JRC|harmonised\s+standard|EN\s?\d|iso\s?\d|再生料"),
]

STATUS_ENUM = ("COVERED", "PARTIAL", "MISSING", "BLOCKED")
STRONG_CLASSES = ("A1", "A2", "B")

#: 已知被阻通道（按线）—— 用于 BLOCKED 判定（有实测依据）
BLOCKED_SOURCES = {
    "end_of_waste": ["iso.org（403 CAPTCHA）", "standards.cencenelec.eu（SPA）"],
    "customs": [],
}


def line_pattern(line_id: str) -> re.Pattern:
    for lid, _name, pat in LINES:
        if lid == line_id:
            return re.compile(pat, re.I)
    raise KeyError(line_id)


def classify_line(record: dict, line_id: str) -> bool:
    pat = line_pattern(line_id)
    hay = ((record.get("title") or "") + "\n" + (record.get("text") or "")[:4000])
    return bool(pat.search(hay))


#: 天然联邦权限线（州级 NOT_APPLICABLE——不得误判为 MISSING；2B1 §12）
FEDERAL_ONLY_LINES = frozenset(("transboundary", "customs"))


def record_class(record: dict) -> str:
    meta = record.get("meta") or {}
    return str(meta.get("acceptance_class") or
               ("B" if record.get("relevant") else "C"))


def gov_level(record: dict) -> str:
    """政府层级（Phase 4B-2B0 Step 8 §九：州不得重复计联邦）。

    federal = 联邦（jurisdiction_of == 'US'）｜state = 州（US-XX）｜
    supra = 欧盟超国家 ｜global = 国际/未知。
    """
    from app.policy.jurisdiction_map import jurisdiction_of
    jid = jurisdiction_of(record)
    if jid == "US":
        return "federal"
    if jid.startswith("US-"):
        return "state"
    if jid == "EU":
        return "supra"
    return "global"


def build_coverage(records: list[dict], *, region: str = "",
                   jurisdiction: str = "",
                   split_level: bool = False) -> dict:
    """六线覆盖矩阵（region 为空=全球视图；'EU'/'US' 过滤；
    jurisdiction 如 'US-CA'/'SE' 时按管辖归属过滤，优先于 region）。

    split_level=True（规格 §九）：US 视图额外拆分联邦/州强证据——
    州级证据**不得**重复计为联邦覆盖，两者独立列示。
    """
    out_lines: list[dict] = []
    for lid, name, _pat in LINES:
        docs = [r for r in records if classify_line(r, lid)]
        if jurisdiction:
            from app.policy.jurisdiction_map import jurisdiction_of
            docs = [r for r in docs if jurisdiction_of(r) == jurisdiction]
        elif region:
            docs = [r for r in docs if _region(r) == region]
        strong = [r for r in docs if record_class(r) in STRONG_CLASSES]
        status = ("COVERED" if strong else ("PARTIAL" if docs else "MISSING"))
        evidence = sorted(
            ({"evidence_id": r.get("evidence_id"), "title": (r.get("title") or "")[:120],
              "source_id": r.get("source_id"), "acceptance_class": record_class(r),
              "url": r.get("url")} for r in strong), key=lambda x: x["evidence_id"])[:5]
        gap = ""
        if status != "COVERED":
            gap = (f"强证据 {len(strong)} 条（弱/背景 {len(docs) - len(strong)} 条）"
                   if docs else "无命中")
            blocked = BLOCKED_SOURCES.get(lid) or []
            if blocked and not docs:
                status = "BLOCKED"
                gap = "通道被阻：" + "；".join(blocked)
    # 修正：region 行组装
        entry = {
            "line_id": lid, "name": name, "region": region or "GLOBAL",
            "documents": len(docs), "strong_documents": len(strong),
            "best_evidence": evidence, "status": status, "gap": gap,
        }
        if split_level:
            fed = [r for r in strong if gov_level(r) == "federal"]
            st = [r for r in strong if gov_level(r) == "state"]
            entry["federal_strong"] = len(fed)
            entry["state_strong"] = len(st)
            entry["federal_ids"] = sorted(
                str(r.get("evidence_id")) for r in fed)[:5]
            entry["state_ids"] = sorted(
                str(r.get("evidence_id")) for r in st)[:5]
            if strong and not fed and st:
                entry["level_note"] = "仅州级强证据——不构成联邦覆盖（州不得计联邦）"
            elif strong and fed and not st:
                if lid in FEDERAL_ONLY_LINES:
                    entry["level_note"] = (
                        "仅联邦强证据——州级 NOT_APPLICABLE_STATE_LEVEL"
                        "（跨境运输/海关属联邦权限，非州缺失）")
                else:
                    entry["level_note"] = "仅联邦强证据——州级待补（州不重复计）"
            elif fed and st:
                entry["level_note"] = (
                    f"联邦 {len(fed)} 条 + 州 {len(st)} 条"
                    "（独立并行，不合并计数）")
        out_lines.append(entry)
    return {
        "lines": out_lines,
        "summary": {
            "total": len(out_lines),
            "covered": sum(1 for l in out_lines if l["status"] == "COVERED"),
            "partial": sum(1 for l in out_lines if l["status"] == "PARTIAL"),
            "missing": sum(1 for l in out_lines if l["status"] == "MISSING"),
            "blocked": sum(1 for l in out_lines if l["status"] == "BLOCKED"),
        },
    }


def _region(record: dict) -> str:
    sid = str(record.get("source_id") or "")
    if sid.startswith("eu_") or sid.startswith("browser_ec"):
        return "EU"
    if sid.startswith("us_") or sid.startswith(("cbp_", "browser_phmsa",
                                                "browser_bci", "browser_calrecycle")):
        return "US"
    if sid.startswith("int_"):
        return "GLOBAL"
    return str(record.get("region") or "")
