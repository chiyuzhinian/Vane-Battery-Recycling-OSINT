# -*- coding: utf-8 -*-
"""跨境/标准层身份（Phase 4B-1 Step 6）—— Basel / OECD / Standards（纯逻辑）。

纪律（规模 §5）：
    · Basel 技术导则：draft ≠ final ≠ binding（draft technical guideline 不得当 binding）
      · COP 决定（Decision BC-x/y）修订附件 → decision / binding
      · 技术导则（guidelines） → official_guidance / non_binding
    · OECD：Decision → binding（对成员具有约束力）；Recommendation/其他 → non_binding
    · Standards 五概念分离（用户口径 2026-09-12）：
      metadata_available / fulltext_available / open_access_status /
      metadata_source_type / endpoint_status
      · EU OJ/JRC 引用 ≠ 标准库接入（角色 ceiling=PARTIAL）
      · HTTP 403/500 ≠ paywalled_known
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.policy.source_access import METADATA_SOURCE_TYPES, OPEN_ACCESS_STATUSES


def basel_status(text: str) -> str:
    """文档阶段：draft / final / adopted / decision / unknown（标题/正文信号）。"""
    t = (text or "").lower()
    if re.search(r"\bdecision\s+bc-\d+", t) or "decision bc-" in t:
        return "decision"
    if re.search(r"\bdraft\b", t):
        return "draft"
    if re.search(r"\b(final|revised)\s+(technical\s+)?guidelines?\b", t):
        return "final"
    if re.search(r"\b(adopted|endorsed)\b", t):
        return "adopted"
    return "unknown"


def basel_instrument(status: str) -> tuple[str, str]:
    """Basel 文档 → (instrument_type, binding_force)。"""
    if status == "decision":
        return ("administrative_rule", "binding")     # COP 决定（修附件）
    return ("official_guidance", "non_binding")       # 技术导则（含 draft）


# ------------------------------------------------------------ OECD

_OECD_DECISION_RE = re.compile(r"\bdecision\b", re.I)
_OECD_RECO_RE = re.compile(r"\brecommendation\b", re.I)


def oecd_instrument(text: str) -> tuple[str, str]:
    """OECD 文书 → (instrument_type, binding_force)。

    OECD Decisions 对成员具有法律约束力（除弃权）；Recommendations 不具约束力。
    """
    t = text or ""
    if _OECD_DECISION_RE.search(t):
        return ("administrative_rule", "binding")
    if _OECD_RECO_RE.search(t):
        return ("official_guidance", "non_binding")
    return ("official_guidance", "non_binding")


# ------------------------------------------------------------ Standards

@dataclass
class StandardRecord:
    publisher: str = ""
    number: str = ""
    title: str = ""
    status: str = ""
    scope: str = ""
    official_url: str = ""
    metadata_available: bool = False
    fulltext_available: bool = False
    paywall_confirmed: bool = False
    metadata_source_type: str = ""
    clause_evidence: list[str] = field(default_factory=list)

    @property
    def open_access_status(self) -> str:
        from app.policy.source_access import resolve_open_access_status
        return resolve_open_access_status(
            fulltext_available=self.fulltext_available,
            metadata_available=self.metadata_available,
            paywall_confirmed=self.paywall_confirmed)

    def as_meta(self) -> dict:
        return {
            "publisher": self.publisher, "standard_number": self.number,
            "standard_title": self.title, "standard_status": self.status,
            "scope": self.scope,
            "metadata_available": self.metadata_available,
            "fulltext_available": self.fulltext_available,
            "open_access_status": self.open_access_status,
            "metadata_source_type": self.metadata_source_type,
            "clause_evidence": self.clause_evidence,
        }


def standard_from_official_reference(*, title: str, url: str, publisher: str = "",
                                     number: str = "", scope: str = "",
                                     source_type: str = "EU_OFFICIAL_REFERENCE",
                                     ) -> StandardRecord:
    """官方引用（EU OJ/JRC 页面）→ 标准元数据记录。

    · metadata_available=True，metadata_source_type 标注来源层级
    · fulltext_available=False（未获取标准全文）
    · clause_evidence 必须为空（不得生成不存在的条款证据）
    """
    if source_type not in METADATA_SOURCE_TYPES:
        raise ValueError(f"metadata_source_type 非法：{source_type!r}")
    return StandardRecord(
        publisher=publisher or "EU official reference", number=number,
        title=title, status="referenced", scope=scope, official_url=url,
        metadata_available=True, fulltext_available=False,
        paywall_confirmed=False, metadata_source_type=source_type)


def assert_valid_standard(rec: StandardRecord) -> None:
    assert rec.open_access_status in OPEN_ACCESS_STATUSES
    if not rec.fulltext_available:
        # 无全文 → 不得带条款证据（fail-fast）
        assert not rec.clause_evidence, "无全文时不得生成条款证据"
