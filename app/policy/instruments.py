# -*- coding: utf-8 -*-
"""文书类型 & 约束力判定（Phase 4A §4）。

判据全部来自 sources/instrument-types.yaml（单一真源）。
核心纪律：
    · PHMSA Safety Advisory → advisory / non_binding（不得冒充 regulation）
    · Information/FAQ/Webinar → information_page/news（不得进入政策主库）
    · Corrigendum → 继承母法类型（剥离前缀后判定）
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.policy.config import load_instruments


@dataclass(frozen=True)
class InstrumentResult:
    instrument_type: str        # regulation / advisory / information_page / unknown …
    binding_force: str          # binding / partially_binding / non_binding / proposal / informational / unknown
    matched: str                # 命中的模式或判例锚点（可复核）
    is_known_case: bool = False


_COMPILED: dict[str, list[re.Pattern]] | None = None
_PRIORITY: list[str] | None = None
_KNOWN: list[tuple[re.Pattern, str, str, str]] | None = None


def _ensure_compiled() -> None:
    global _COMPILED, _PRIORITY, _KNOWN
    if _COMPILED is not None:
        return
    cfg = load_instruments()
    _COMPILED = {
        it.id: [re.compile(p, re.I) for p in it.detect_patterns]
        for it in cfg.instrument_types
    }
    _PRIORITY = list(cfg.priority)
    _KNOWN = [
        (re.compile(re.escape(kc.match), re.I), kc.instrument_type,
         kc.binding_force, kc.note)
        for kc in cfg.known_cases
    ]


_CORRIGENDUM_RE = re.compile(r"^\s*corrigendum\s+to\s+", re.I)


def detect_instrument(title: str, text: str = "") -> InstrumentResult:
    """标题优先判定；corrigendum 继承母法；多信号按语义优先级取先命中。"""
    _ensure_compiled()
    assert _COMPILED is not None and _PRIORITY is not None and _KNOWN is not None
    t = title or ""

    # 0) 判例锚点（回归锁定，最高优先）
    for rx, itype, bf, _note in _KNOWN:
        if rx.search(t):
            return InstrumentResult(itype, bf, f"known_case:{rx.pattern[:40]}", True)

    # 1) corrigendum：剥离前缀后按母法判定（类型继承）
    m = _CORRIGENDUM_RE.search(t)
    stripped = t[m.end():] if m else t

    # 2) 按语义优先级扫描
    by_id = load_instruments().by_id()
    for itype in _PRIORITY:
        for rx in _COMPILED.get(itype, []):
            if rx.search(stripped):
                bf = by_id[itype].binding_force
                prefix = "inherited:" if m else ""
                return InstrumentResult(itype, bf, f"{prefix}{rx.pattern[:40]}")

    # 3) 兜底：正文里出现 information 页信号的（极少），否则 unknown
    if re.search(r"\b(faq|frequently\s+asked)\b", text or "", re.I):
        return InstrumentResult("information_page", "informational", "text:faq")
    return InstrumentResult("unknown", "unknown", "")


def instrument_of_evidence(record: dict) -> InstrumentResult:
    """记录 → 文书类型。meta 中已存的（backfill 后）优先，否则现算。"""
    meta = record.get("meta") or {}
    it = record.get("instrument_type") or meta.get("instrument_type")
    if it:
        bf = record.get("binding_force") or meta.get("binding_force") or "unknown"
        return InstrumentResult(str(it), str(bf), "record:precomputed")
    return detect_instrument(record.get("title") or "",
                             record.get("text") or "")
