# -*- coding: utf-8 -*-
"""Legal Identity Resolver（Phase 4A §7）。

解析并校验每条政策记录的**文档级身份**：
    canonical_id / jurisdiction / official_title / original_title /
    instrument_type / binding_force / issuer / publication_date /
    effective_date / status / official_url / official_identifier / language

纪律：Source official ≠ document verified；身份必须单独解析与校验。
兼容：缺失字段**不报错**——按 available 标记（backfill 前旧数据大量缺字段）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.policy.instruments import detect_instrument

LEGAL_STATUSES = ("effective", "not_yet_effective", "amended", "repealed",
                  "replaced", "expired", "proposal", "draft", "unknown")

REQUIRED_FIELDS = ("canonical_id", "jurisdiction", "official_title",
                   "instrument_type", "binding_force", "official_identifier",
                   "official_url", "status")

_ISSUER_PATTERNS = [
    (r"commission\s+delegated\s+regulation", "European Commission"),
    (r"commission\s+implementing\s+regulation", "European Commission"),
    (r"commission\s+notice", "European Commission"),
    (r"directive\s*\\(EU\\)|regulation\s*\\(EU\\)", "European Parliament and Council"),
    (r"pipeline\s+and\s+hazardous\s+materials", "PHMSA"),
    (r"department\s+of\s+energy|\\bDOE\\b", "US DOE"),
    (r"environmental\s+protection\s+agency|\\bEPA\\b", "US EPA"),
    (r"internal\s+revenue\s+service|\\bIRS\\b", "US IRS"),
    (r"occupational\s+safety", "US OSHA"),
]

_REPEAL_RE = re.compile(r"\brepealing\b", re.I)
_PROPOSAL_RE = re.compile(r"^\s*proposal\s+for|\bCOM\(\d{4}\)|\d{4}PC\d+|52\d{3}PC", re.I)
_CORRIGENDUM_RE = re.compile(r"^\s*corrigendum", re.I)
_AMENDING_RE = re.compile(r"\bamending\b", re.I)


@dataclass
class LegalIdentity:
    canonical_id: str = ""
    jurisdiction: str = ""
    official_title: str = ""
    original_title: str = ""
    instrument_type: str = "unknown"
    binding_force: str = "unknown"
    issuer: str = ""
    publication_date: str | None = None
    effective_date: str | None = None
    status: str = "unknown"
    official_url: str = ""
    official_identifier: str = ""
    language: str = "unknown"
    available: bool = False
    missing_fields: list[str] = field(default_factory=list)


def _detect_status(record: dict) -> str:
    title = record.get("title") or ""
    meta = record.get("meta") or {}
    if _PROPOSAL_RE.search(title):
        return "proposal"
    if record.get("source_id", "").startswith("eu_nim_"):
        return "effective"          # 转化措施=已生效（历史法按 amended 处理依据 title）
    in_force = str(meta.get("in_force", "")).strip()
    if in_force == "1":
        return "effective"
    if in_force == "0":
        return "repealed"
    if _CORRIGENDUM_RE.search(title):
        return "effective"
    if _REPEAL_RE.search(title):
        return "effective"          # 本身有效（repeals 他法）
    if _AMENDING_RE.search(title):
        return "effective"
    return "unknown"


def _detect_jurisdiction(record: dict) -> str:
    sid = str(record.get("source_id") or "")
    m = re.match(r"eu_nim_([a-z]{2})$", sid)
    if m:
        return m.group(1).upper()
    if sid in ("eur_lex", "eu_eurlex_battery_reg", "eu_eurlex_keyword",
               "eu_eurlex_elv", "eu_eurlex_waste_shipment", "eu_eurlex_crm",
               "browser_echa"):
        return "EU"
    if sid.startswith("us_") or sid.startswith("browser_"):
        return {"browser_phmsa": "US", "browser_bci": "US",
                "browser_calrecycle": "US-CA",
                "browser_netherlands": "NL", "browser_france": "FR",
                "browser_echa": "EU"}.get(sid, "US" if sid.startswith("us_") else "ZZ")
    return {"de_gesetze": "DE", "nl_bwb": "NL", "es_boe": "ES",
            "fr_dila": "FR", "fr_ademe_opendata": "FR"}.get(sid, "ZZ")


def resolve_identity(record: dict) -> LegalIdentity:
    title = record.get("title") or ""
    meta = record.get("meta") or {}
    inst = detect_instrument(title, record.get("text") or "")

    celex = str(meta.get("celex") or "")
    nim = str(meta.get("nim_id") or "")
    fr_doc = str(meta.get("document_number") or "")
    eid = str(record.get("evidence_id") or "")

    ident = LegalIdentity(
        canonical_id=celex or (f"NIM:{nim}" if nim else (fr_doc or eid)),
        jurisdiction=_detect_jurisdiction(record),
        official_title=title,
        original_title=title,
        instrument_type=inst.instrument_type,
        binding_force=inst.binding_force,
        issuer=next((name for rx, name in
                     [(re.compile(p, re.I), n) for p, n in _ISSUER_PATTERNS]
                     if rx.search(title)), ""),
        publication_date=record.get("publish_date"),
        effective_date=meta.get("entry_into_force") or record.get("publish_date"),
        status=_detect_status(record),
        official_url=record.get("url") or "",
        official_identifier=celex or nim or fr_doc or eid,
        language=str(meta.get("lang") or meta.get("title_lang") or "unknown"),
        available=bool(title and (celex or nim or fr_doc or eid)),
    )
    ident.missing_fields = [f for f in REQUIRED_FIELDS
                            if not getattr(ident, f) or getattr(ident, f) == "unknown"]
    return ident


def identity_completeness(records: list[dict]) -> dict:
    total = len(records)
    if not total:
        return {"total": 0, "complete": 0, "pct": 0.0}
    complete = 0
    for r in records:
        ident = resolve_identity(r)
        if len(ident.missing_fields) <= 2:      # 容差：允许 <=2 个次要字段缺
            complete += 1
    return {"total": total, "complete": complete,
            "pct": round(100.0 * complete / total, 1)}
