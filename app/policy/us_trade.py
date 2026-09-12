# -*- coding: utf-8 -*-
"""US 贸易源（CBP CROSS / BIS）身份与文书类型（Phase 4B-1 Step 5）—— 纯逻辑。

纪律（规格 §4-4/§4-5）：
    · CBP 裁定（ruling）**不是** regulation → official_guidance / non_binding
    · CROSS API 是**模糊检索**（实测：搜 battery 会带回巧克力/甘草糖裁定）→ 必须主题过滤
    · BIS 文书经 FR 通道时按官方 type 区分：Rule→administrative_rule、Proposed Rule→proposal、
      Notice 等宽泛类型不猜（Step 8 统一处理）
"""
from __future__ import annotations

import re
from datetime import datetime

#: CROSS 裁定一律按"官方指引"处理（海关归类裁定不是立法）
RULING_INSTRUMENT = ("official_guidance", "non_binding")


def _words(term: str) -> list[str]:
    return [w for w in re.split(r"\s+", (term or "").strip().lower()) if len(w) > 1]


def subject_matches(subject: str, term: str) -> bool:
    """整词共现（压掉 CROSS 的模糊检索噪声）。"""
    words = _words(term)
    if not words:
        return True
    s = (subject or "").lower()
    return all(re.search(rf"\b{re.escape(w)}", s) for w in words)


def parse_cross_rulings(payload: dict, *, term: str) -> list[dict]:
    """CROSS /api/search JSON → 规范化裁定的列表（含主题过滤）。"""
    out: list[dict] = []
    for r in (payload or {}).get("rulings") or []:
        subject = str(r.get("subject") or "").strip()
        if not subject_matches(subject, term):
            continue
        out.append({
            "ruling_number": str(r.get("rulingNumber") or "").strip(),
            "subject": subject,
            "categories": str(r.get("categories") or "").strip(),
            "collection": str(r.get("collection") or "").strip(),
            "ruling_date": str(r.get("rulingDate") or "")[:10],
            "tariffs": r.get("tariffs") or [],
            "modifies": r.get("modifies") or [],
            "revoked_by": r.get("revokedBy") or [],
        })
    return [x for x in out if x["ruling_number"]]


def cross_record(ruling: dict) -> dict:
    """裁定 → 记录（未判定的草稿；classification 由 acceptance 统一做）。"""
    num = ruling["ruling_number"]
    itype, bforce = RULING_INSTRUMENT
    return {
        "evidence_id": f"us_cbp_{num}",
        "channel": "connector",
        "source_id": "cbp_cross",
        "region": "US",
        "url": f"https://rulings.cbp.gov/ruling/{num}",
        "title": f"CBP Ruling {num} — {ruling['subject'][:160]}",
        "publish_date": ruling.get("ruling_date") or "",
        "meta": {
            "region": "US",
            "collector": "collect_us_trade_sources",
            "ruling_number": num,
            "categories": ruling.get("categories", ""),
            "collection": ruling.get("collection", ""),
            "ruling_date": ruling.get("ruling_date", ""),
            "tariffs": ruling.get("tariffs", [])[:10],
            # 裁定类型显式记录（判定器可复核；不得冒充 regulation）
            "instrument_type": itype,
            "binding_force": bforce,
            "instrument_source": "CROSS API（裁定=官方指引）",
        },
        "text": "\n".join(filter(None, [
            ruling["subject"], f"Categories: {ruling.get('categories','')}",
            f"Ruling date: {ruling.get('ruling_date','')}",
        ]))[:4000],
    }


def parse_ruling_date(text: str) -> datetime | None:
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
