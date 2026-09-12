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

# ---- 官方元数据优先（Step 8）：官方字段 → 文书类型（仅映射明确的）----
#   FR 官方 type（Step 2 实测）：Rule / Proposed Rule 明确；Notice 等不猜
_FR_TYPE_MAP: dict[str, tuple[str, str]] = {
    "rule": ("administrative_rule", "binding"),
    "proposed rule": ("proposal", "proposal"),
}
#   CELEX 类型位（3yyyy[RDL]nnnn）：R=条例 L=指令 D=决定
_CELEX_OFFICIAL_RE = re.compile(r"^3(\d{4})([RLD])(\d{4})")
_CELEX_TYPE_MAP = {"R": ("regulation", "binding"),
                   "L": ("directive", "binding"),
                   "D": ("administrative_rule", "binding")}
#   提案：5yyyyPCnnnn / COM(…)
_CELEX_PROPOSAL_RE = re.compile(r"^(?:5\d{4}PC\d+|52\d{3}PC)")


def instrument_from_metadata(meta: dict | None) -> InstrumentResult | None:
    """官方元数据 → 文书类型（仅强信号；不猜）。

    · FR 官方 type：Rule / Proposed Rule（GPO 分类，强）
    · CELEX 提案位（5yyyyPC）：强
    · CELEX 类型位（R/L/D）**不在此处理**——它分辨不出 delegated/implementing
      （实测：32025R0606 = Delegated Regulation，但类型位是 R），
      只能作标题无信号时的回退（见 detect_instrument 第 5 步）
    """
    meta = meta or {}
    fr_type = str(meta.get("type") or "").strip().lower()
    if fr_type in _FR_TYPE_MAP:
        itype, bf = _FR_TYPE_MAP[fr_type]
        return InstrumentResult(itype, bf, f"meta:fr_type={fr_type}", False)
    celex = str(meta.get("celex") or "").strip()
    if celex and _CELEX_PROPOSAL_RE.match(celex):
        return InstrumentResult("proposal", "proposal",
                                f"meta:celex={celex[:10]}", False)
    return None


#: NIM 母语文书类型（官方公报标题里的法律形式词）—— 只在 NIM 记录/母语标题上使用
_NIM_DOC_TYPES = (
    (r"\bvyhl\u00e1[\u0161s]ka\b|\bna[\u0159]\u00edzen\u00ed\b",
     "administrative_rule", "binding"),                     # CZ 法令/政府令
    (r"\bz\u00e1kon\b", "statute", "binding"),              # CZ 法律
    (r"\bVerordnung\b", "administrative_rule", "binding"),  # DE 条例
    (r"\bGesetz\b", "statute", "binding"),                  # DE 法律
    (r"\bd\u00e9cret\b|\barr\u00eat\u00e9\b", "administrative_rule", "binding"),  # FR
    (r"\breal decreto\b", "administrative_rule", "binding"),  # ES
    (r"\bbesluit\b", "administrative_rule", "binding"),     # NL
)

#: 结构化官方文档形状（官方标题范式，不是 URL 硬编码）
_STRUCTURED_SHAPES = (
    (re.compile(r"^\d+\s+CFR\s+Part\s", re.I), "regulation", "binding"),      # eCFR
    (re.compile(r"^U\.S\.C\.\s*Title\s+\d+", re.I), "statute", "binding"),    # USC
    (re.compile(r"^Public Law\s+\d+-\d+", re.I), "statute", "binding"),       # PLAW
    (re.compile(r"^CBP Ruling\s", re.I), "official_guidance", "non_binding"), # CROSS
)


def instrument_from_nim_title(title: str) -> InstrumentResult | None:
    for pat, itype, bf in _NIM_DOC_TYPES:
        if re.search(pat, title, re.I):
            return InstrumentResult(itype, bf, f"nim_doc_type:{pat[:24]}", False)
    return None


def instrument_from_shape(title: str) -> InstrumentResult | None:
    for rx, itype, bf in _STRUCTURED_SHAPES:
        if rx.search(title or ""):
            return InstrumentResult(itype, bf, f"shape:{rx.pattern[:24]}", False)
    return None


def _celex_fallback(meta: dict | None) -> InstrumentResult | None:
    celex = str((meta or {}).get("celex") or "").strip()
    m = _CELEX_OFFICIAL_RE.match(celex) if celex else None
    if m:
        itype, bf = _CELEX_TYPE_MAP[m.group(2)]
        return InstrumentResult(itype, bf, f"meta:celex_fallback={celex[:10]}", False)
    return None


def detect_instrument(title: str, text: str = "",
                      meta: dict | None = None) -> InstrumentResult:
    """判定顺序（Step 8 metadata-first + 标题语义，逐层记录信号）：

        0) 判例锚点（回归锁定）
        1) FR 官方 type（Rule/Proposed Rule）/ CELEX 提案位 —— 强证据
        2) NIM 母语文书类型（vyhláška/Verordnung/…）
        3) 结构化官方形状（CFR Part / USC / Public Law / CBP Ruling）
        4) corrigendum 剥离 → 标题语义优先级扫描（delegated/implementing/guidance…）
        5) CELEX 类型位回退（仅当标题无信号）
        6) FAQ 兜底 → unknown

    纪律：AI 可辅助分类，但**不得**单独决定 binding force。
    """
    _ensure_compiled()
    assert _COMPILED is not None and _PRIORITY is not None and _KNOWN is not None
    t = title or ""

    # 0) 判例锚点（回归锁定，最高优先）
    for rx, itype, bf, _note in _KNOWN:
        if rx.search(t):
            return InstrumentResult(itype, bf, f"known_case:{rx.pattern[:40]}", True)

    # 1) 官方元数据强信号
    official = instrument_from_metadata(meta)
    if official is not None:
        return official

    # 2) NIM 母语文书类型（NIM 记录或母语法律形式词）
    if re.search(r"vyhl\u00e1[\u0161s]ka|z\u00e1kon|Verordnung|d\u00e9cret|"
                 r"arr\u00eat\u00e9|besluit|real decreto", t, re.I):
        nim = instrument_from_nim_title(t)
        if nim is not None:
            return nim

    # 3) 结构化官方形状
    shape = instrument_from_shape(t)
    if shape is not None:
        return shape

    # 4) corrigendum 剥离 → 标题优先级扫描
    m = _CORRIGENDUM_RE.search(t)
    stripped = t[m.end():] if m else t
    by_id = load_instruments().by_id()
    for itype in _PRIORITY:
        for rx in _COMPILED.get(itype, []):
            if rx.search(stripped):
                bf = by_id[itype].binding_force
                prefix = "inherited:" if m else ""
                return InstrumentResult(itype, bf, f"{prefix}{rx.pattern[:40]}")

    # 5) CELEX 类型位回退（标题无信号时）
    fb = _celex_fallback(meta)
    if fb is not None:
        return fb

    # 6) 兜底
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
                             record.get("text") or "", meta)
