# -*- coding: utf-8 -*-
"""CFR 身份与关系（Phase 4B-1 Step 3）—— 纯逻辑，无网络。

数据源：eCFR versioner API（官方 XML，实测 200）
    GET https://www.ecfr.gov/api/versioner/v1/full/{date}/title-{n}.xml?part={p}

实测结构（2026-09-12，见 outputs/cache/ecfr/*.xml）：
    <DIV8 N="273.1" TYPE="SECTION" hierarchy_metadata="{...citation: 40 CFR 273.1...}">
      <HEAD>…</HEAD> …
    <AUTH><HED>Authority:</HED>49 U.S.C. 5101 et seq.; Pub. L. 109-59 …</AUTH>

职责：
    · canonical id：CFR:{title}:{part} ／ CFR:{title}:{section}
    · 解析 Title / Part / Section / Authority / USC 引用 / Pub. L. 引用 / FR 引用
    · FR → codified_in → CFR 链接（FR 官方 cfr_references 为证据）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:                                    # lxml 可用时优先（requirements 已声明）
    from lxml import etree as _ET
except Exception:                       # pragma: no cover — 兜底 stdlib
    import xml.etree.ElementTree as _ET   # type: ignore


def part_key(title: int | str, part: int | str) -> str:
    return f"CFR:{title}:{part}"


def section_key(title: int | str, section: str) -> str:
    """section 为完整编号（含 part 前缀），如 "273.1"。"""
    return f"CFR:{title}:{section}"


# ------------------------------------------------------------ 引用抽取

_USC_RE = re.compile(
    r"\b(\d{1,2})\s+U\.?\s?S\.?\s?C\.?\s+(?:§+\s*)?"
    r"(\d+[A-Za-z]?(?:\([a-zA-Z0-9]+\))*)", re.I)
_PL_RE = re.compile(r"Pub\.?\s*L\.?\s*(\d{1,3})\s*[–\-—]\s*(\d{1,4})", re.I)
_FR_RE = re.compile(r"\b(\d{2,3})\s+FR\s+(\d{1,6})\b")


def extract_usc_citations(text: str) -> list[str]:
    out: list[str] = []
    for m in _USC_RE.finditer(text or ""):
        cite = f"{m.group(1)} U.S.C. {m.group(2)}"
        if cite not in out:
            out.append(cite)
    return out


def extract_public_laws(text: str) -> list[str]:
    out: list[str] = []
    for m in _PL_RE.finditer(text or ""):
        cite = f"PL {int(m.group(1))}-{int(m.group(2))}"
        if cite not in out:
            out.append(cite)
    return out


def extract_fr_citations(text: str) -> list[str]:
    out: list[str] = []
    for m in _FR_RE.finditer(text or ""):
        cite = f"{m.group(1)} FR {m.group(2)}"
        if cite not in out:
            out.append(cite)
    return out


# ------------------------------------------------------------ Part 解析

@dataclass
class CfrSection:
    number: str
    heading: str

    @property
    def citation_suffix(self) -> str:
        return self.number


@dataclass
class CfrPart:
    title: int
    part: str
    heading: str = ""
    authority: str = ""
    sections: list[CfrSection] = field(default_factory=list)
    usc_citations: list[str] = field(default_factory=list)
    public_laws: list[str] = field(default_factory=list)
    fr_citations: list[str] = field(default_factory=list)
    currentness: str = ""

    @property
    def key(self) -> str:
        return part_key(self.title, self.part)

    @property
    def canonical_title(self) -> str:
        head = self.heading.replace("&#x2014;", "—").strip()
        return f"{self.title} CFR Part {self.part}" + (f" — {head}" if head else "")


def _text_of(el) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def parse_part_document(xml_text: str, *, title: int, part: str,
                        currentness: str = "") -> CfrPart:
    """eCFR Part XML → CfrPart（失败抛 ValueError，交由调用方记 PARSER_FAILURE）。"""
    try:
        root = _ET.fromstring(xml_text.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"XML 解析失败: {exc}") from exc

    out = CfrPart(title=title, part=str(part), currentness=currentness)
    for div in root.iter():
        tag = div.tag if isinstance(div.tag, str) else ""
        if tag == "HEAD" and not out.heading:
            txt = _text_of(div)
            if txt and "PART" not in txt.upper()[:12]:
                out.heading = txt
            elif txt:
                out.heading = txt.split("—", 1)[-1].strip() if "—" in txt else txt
        if tag == "DIV8":
            num = (div.get("N") or "").strip()
            if not num:
                continue
            head = ""
            for child in div:
                if isinstance(child.tag, str) and child.tag == "HEAD":
                    head = _text_of(child)
                    break
            out.sections.append(CfrSection(number=num, heading=head))

    auth_parts: list[str] = []
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag == "AUTH":
            auth_parts.append(_text_of(el))
    out.authority = " ".join(auth_parts).strip()
    if out.authority.startswith("Authority:"):
        out.authority = out.authority[len("Authority:"):].strip()

    hay = out.authority + " " + out.heading
    out.usc_citations = extract_usc_citations(hay)
    out.public_laws = extract_public_laws(hay)
    out.fr_citations = extract_fr_citations(hay)
    return out


# ------------------------------------------------------------ FR → CFR 链接

def build_fr_cfr_links(fr_overlay_rows: dict[str, dict]) -> list[dict]:
    """FR 记录（含官方 cfr_references）→ codified_in 边。

    输入为 fr_identity_overlay 行：{evidence_id, fr_identity:{cfr_references:[{title,part}]}}
    证据类型固定为官方字段（FR API cfr_references），不得由标题猜测。
    """
    links: list[dict] = []
    for eid, row in (fr_overlay_rows or {}).items():
        fr = row.get("fr_identity") or {}
        for ref in fr.get("cfr_references") or []:
            title, part = ref.get("title"), ref.get("part")
            if title is None or part in (None, ""):
                continue
            links.append({
                "evidence_id": eid,
                "document_number": row.get("document_number")
                or fr.get("fr_document_number", ""),
                "citation": fr.get("fr_citation", ""),
                "relation": "codified_in",
                "cfr_key": part_key(title, part),
                "cfr_title": int(title) if str(title).isdigit() else title,
                "cfr_part": str(part),
                "relation_evidence": "FR API cfr_references（官方字段）",
            })
    return links


def link_coverage(links: list[dict], ecfr_part_keys: set[str]) -> dict:
    """链接覆盖率：FR 指向的 CFR part 有多少已在 eCFR 侧核验存在。"""
    total = len(links)
    matched = [l for l in links if l["cfr_key"] in ecfr_part_keys]
    unique_parts = sorted({l["cfr_key"] for l in links})
    unmatched_parts = sorted({l["cfr_key"] for l in links
                              if l["cfr_key"] not in ecfr_part_keys})
    return {
        "links_total": total,
        "unique_cfr_parts": len(unique_parts),
        "matched_links": len(matched),
        "matched_pct": round(100.0 * len(matched) / total, 1) if total else 0.0,
        "unique_parts": unique_parts,
        "unmatched_parts": unmatched_parts,
        "examples": [
            {"cfr_key": l["cfr_key"], "from": l["document_number"], "citation": l["citation"]}
            for l in matched[:10]
        ],
    }
