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


def record_class(record: dict) -> str:
    meta = record.get("meta") or {}
    return str(meta.get("acceptance_class") or
               ("B" if record.get("relevant") else "C"))


def build_coverage(records: list[dict], *, region: str = "") -> dict:
    """六线覆盖矩阵（region 为空=全球视图；'EU'/'US' 过滤）。"""
    out_lines: list[dict] = []
    for lid, name, _pat in LINES:
        docs = [r for r in records if classify_line(r, lid)]
        if region:
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
        out_lines.append({
            "line_id": lid, "name": name, "region": region or "GLOBAL",
            "documents": len(docs), "strong_documents": len(strong),
            "best_evidence": evidence, "status": status, "gap": gap,
        })
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
