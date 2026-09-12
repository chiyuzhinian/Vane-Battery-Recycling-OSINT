# -*- coding: utf-8 -*-
"""US Federal Legal Identity（Phase 4B-1 Step 2）—— FR 官方元数据优先。

数据源（已实测 200，无需 API Key）：
    GET https://www.federalregister.gov/api/v1/documents/{document_number}.json

实测字段（2026-09-12，夹具 tests/phase4b1/fixtures/fr_*.json）：
    document_number / citation("84 FR 8006") / type("Rule") / subtype /
    action / cfr_references[{title,part,chapter}] / regulation_id_numbers[] /
    docket_ids[] / effective_on / publication_date / volume / start_page /
    end_page / agencies[] / topics[] / html_url / pdf_url / raw_text_url

纪律：
    · US 联邦身份不能只有 title+URL（规格 §6）——必须解析官方标识
    · instrument_type 只对官方明确情形下结论（Rule→administrative_rule /
      Proposed Rule→proposal）；Notice 等宽泛类型**不猜**（留待 Step 8 metadata 全量）
    · cfr_references 是 FR→CFR 关系（codified_in）的官方证据（Step 3 消费）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

#: FR type → (instrument_type, binding_force)；仅映射官方明确的两种，其余不猜
FR_TYPE_INSTRUMENT: dict[str, tuple[str, str]] = {
    "Rule": ("administrative_rule", "binding"),
    "Proposed Rule": ("proposal", "proposal"),
}


@dataclass
class FrIdentity:
    document_number: str = ""
    citation: str = ""
    fr_type: str = ""
    subtype: str = ""
    action: str = ""
    rin: list[str] = field(default_factory=list)
    docket_ids: list[str] = field(default_factory=list)
    cfr_references: list[dict] = field(default_factory=list)
    agencies: list[str] = field(default_factory=list)
    effective_on: str = ""
    publication_date: str = ""
    volume: str = ""
    start_page: int | None = None
    end_page: int | None = None
    topics: list[str] = field(default_factory=list)
    html_url: str = ""
    pdf_url: str = ""
    raw_text_url: str = ""
    instrument_type: str = ""
    binding_force: str = ""
    legal_status: str = "unknown"
    issuer: str = ""
    ambiguous: bool = False
    issues: list[str] = field(default_factory=list)

    # ---- 派生 ----
    @property
    def canonical_id(self) -> str:
        return f"FR:{self.document_number}" if self.document_number else ""

    @property
    def official_identifier(self) -> str:
        return self.citation or self.document_number

    def as_dict(self) -> dict:
        d = dict(self.__dict__)
        d["canonical_id"] = self.canonical_id
        d["official_identifier"] = self.official_identifier
        return d


def _norm_part(part) -> str:
    return str(part).strip() if part is not None else ""


def _today() -> date:
    return datetime.now().date()


def parse_fr_document(payload: dict, *, today: date | None = None) -> FrIdentity:
    """FR 单文档 JSON → FrIdentity（官方字段直取，不推断）。"""
    out = FrIdentity()
    if not isinstance(payload, dict):
        out.ambiguous = True
        out.issues.append("payload 不是对象")
        return out

    out.document_number = str(payload.get("document_number") or "").strip()
    out.citation = str(payload.get("citation") or "").strip()
    out.fr_type = str(payload.get("type") or "").strip()
    out.subtype = str(payload.get("subtype") or "").strip()
    out.action = str(payload.get("action") or "").strip()
    out.rin = [str(x) for x in (payload.get("regulation_id_numbers") or [])]
    out.docket_ids = [str(x) for x in (payload.get("docket_ids") or [])]
    out.effective_on = str(payload.get("effective_on") or "").strip()
    out.publication_date = str(payload.get("publication_date") or "").strip()
    out.volume = str(payload.get("volume") or "").strip()
    out.start_page = payload.get("start_page")
    out.end_page = payload.get("end_page")
    out.topics = [str(x) for x in (payload.get("topics") or [])]
    out.html_url = str(payload.get("html_url") or "").strip()
    out.pdf_url = str(payload.get("pdf_url") or "").strip()
    out.raw_text_url = str(payload.get("raw_text_url") or "").strip()

    for ref in payload.get("cfr_references") or []:
        if not isinstance(ref, dict):
            continue
        title = ref.get("title")
        part = _norm_part(ref.get("part"))
        if title is None or part == "":
            continue
        out.cfr_references.append({
            "title": int(title) if str(title).isdigit() else title,
            "part": part,
            "chapter": ref.get("chapter"),
        })

    out.agencies = [
        str(a.get("name") or a.get("raw_name") or "").strip()
        for a in (payload.get("agencies") or []) if isinstance(a, dict)
    ]
    out.agencies = [a for a in out.agencies if a]
    out.issuer = out.agencies[0] if out.agencies else ""

    # ---- 官方明确类型才映射 ----
    mapped = FR_TYPE_INSTRUMENT.get(out.fr_type)
    if mapped:
        out.instrument_type, out.binding_force = mapped
    else:
        out.issues.append(f"FR type 未映射（留待 Step 8）：{out.fr_type!r}")

    # ---- 法律状态（官方日期直取）----
    if out.fr_type == "Proposed Rule":
        out.legal_status = "proposal"
    elif out.effective_on:
        try:
            eff = datetime.strptime(out.effective_on, "%Y-%m-%d").date()
            out.legal_status = "effective" if eff <= (today or _today()) \
                else "not_yet_effective"
        except ValueError:
            out.legal_status = "unknown"
            out.issues.append(f"effective_on 解析失败：{out.effective_on!r}")
    else:
        out.legal_status = "unknown"

    # ---- 歧义判定 ----
    if not out.document_number:
        out.ambiguous = True
        out.issues.append("缺少 document_number")
    if not out.citation:
        out.issues.append("缺少 citation（官方标识降级为 document_number）")
        out.ambiguous = True
    return out


def identity_fields_from_fr(fr: FrIdentity, *, today: date | None = None) -> dict:
    """输出可直接并入 overlay 的 identity 字段（US 侧，官方元数据）。"""
    return {
        "canonical_id": fr.canonical_id,
        "official_identifier": fr.official_identifier,
        "fr_document_number": fr.document_number,
        "fr_citation": fr.citation,
        "fr_type": fr.fr_type,
        "fr_subtype": fr.subtype,
        "fr_action": fr.action,
        "fr_rin": fr.rin,
        "fr_docket_ids": fr.docket_ids,
        "cfr_references": fr.cfr_references,
        "fr_agencies": fr.agencies,
        "fr_effective_on": fr.effective_on,
        "fr_publication_date": fr.publication_date,
        "fr_volume": fr.volume,
        "fr_start_page": fr.start_page,
        "fr_end_page": fr.end_page,
        "fr_html_url": fr.html_url,
        "fr_pdf_url": fr.pdf_url,
        "fr_raw_text_url": fr.raw_text_url,
        "identity_status": fr.legal_status,
    }


def cfr_keys(fr: FrIdentity) -> list[str]:
    """FR→CFR 链接键（codified_in 目标：CFR:{title}:{part}）。"""
    return [f"CFR:{r['title']}:{r['part']}" for r in fr.cfr_references]
