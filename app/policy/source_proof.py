# -*- coding: utf-8 -*-
"""Source Proof（Phase 4B-2A Step 4）—— 纯逻辑模型与构建。

流程铁律（规格 §十二）：Source Mapping → endpoint probe → 3–10 真实文书样本
→ 确认 identity/status/全文/检索能力 → **才允许开发 connector**。

source_proof 字段：
    official_owner / official_domain / source_role / access_method
    search_available / enumeration_available / metadata_available / fulltext_available
    language / sample_urls[] / known_limitations[] / probe / verified_at

能力判定（证据驱动，全部测试锁定）：
    fulltext_available      ← ≥1 样本 200 且正文 >2000 字节
    metadata_available      ← ≥1 样本可提取标题
    search_available        ← ≥1 检索尝试 200 且解析出 ≥1 文书链接
    enumeration_available   ← search_available 或入口页解析出 ≥1 文书链接
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent.parent
PROOFS_DIR = ROOT / "outputs" / "audit" / "source_proofs"

MIN_FULLTEXT_BYTES = 2000


class SourceConfig(BaseModel):
    source_role: str
    source_id: str
    official_owner: str = ""
    official_domain: str = ""
    access_method: str = "html"
    entry_url: str = ""
    search_attempts: list[str] = Field(default_factory=list)
    samples_known: list[str] = Field(default_factory=list)
    note: str = ""


class JurisdictionSources(BaseModel):
    version: int
    jurisdiction_id: str
    language: str
    link_keywords: str
    link_include: list[str] = Field(default_factory=list)
    sources: list[SourceConfig]


class SampleEvidence(BaseModel):
    url: str
    title: str = ""
    status: int | None = None
    bytes: int = 0
    error: str = ""
    source: str = "extracted"          # extracted | known


class SearchEvidence(BaseModel):
    url: str
    status: int | None = None
    bytes: int = 0
    links_extracted: int = 0
    error: str = ""
    sample_links: list[str] = Field(default_factory=list)


class SourceProof(BaseModel):
    source_role: str
    source_id: str
    official_owner: str = ""
    official_domain: str = ""
    access_method: str = ""
    language: str = ""
    entry_url: str = ""
    probe: dict = Field(default_factory=dict)
    searches: list[SearchEvidence] = Field(default_factory=list)
    samples: list[SampleEvidence] = Field(default_factory=list)
    capabilities: dict = Field(default_factory=dict)
    known_limitations: list[str] = Field(default_factory=list)
    verified_at: str = ""

    def as_dict(self) -> dict:
        return self.model_dump()


def derive_capabilities(searches: list[SearchEvidence],
                        samples: list[SampleEvidence],
                        entry_links: int = 0) -> dict:
    ok_samples = [s for s in samples if s.status == 200 and s.bytes > 0]
    fulltext = any(s.status == 200 and s.bytes > MIN_FULLTEXT_BYTES
                   for s in samples)
    metadata = any(s.title for s in ok_samples)
    search = any(s.status == 200 and s.links_extracted > 0 for s in searches)
    enumeration = search or entry_links > 0
    return {
        "search_available": search,
        "enumeration_available": enumeration,
        "metadata_available": metadata,
        "fulltext_available": fulltext,
    }


def build_limitations(searches: list[SearchEvidence],
                      samples: list[SampleEvidence],
                      entry_links: int = 0) -> list[str]:
    out: list[str] = []
    for s in searches:
        if s.error:
            out.append(f"检索尝试失败（{s.error}）：{s.url}")
        elif s.status != 200:
            out.append(f"检索尝试 HTTP {s.status}：{s.url}")
        elif s.links_extracted == 0:
            out.append(f"检索页无可解析文书链接（可能 JS 渲染/参数错误）：{s.url}")
    for s in samples:
        if s.error:
            out.append(f"样本抓取失败（{s.error}）：{s.url}")
        elif s.status != 200:
            out.append(f"样本 HTTP {s.status}：{s.url}")
    if entry_links == 0 and not searches:
        out.append("入口页未解析出文书链接且无检索尝试（能力受限）")
    return out


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_proof(jid: str, proofs: list[SourceProof],
                extra: dict | None = None) -> Path:
    import json
    PROOFS_DIR.mkdir(parents=True, exist_ok=True)
    fp = PROOFS_DIR / f"{jid}.json"
    payload = {
        "jurisdiction_id": jid,
        "generated_at": now_utc(),
        "sources": [p.as_dict() for p in proofs],
        "summary": {
            "sources": len(proofs),
            "search_available": sum(1 for p in proofs
                                    if p.capabilities.get("search_available")),
            "fulltext_available": sum(1 for p in proofs
                                      if p.capabilities.get("fulltext_available")),
            "samples_total": sum(len(p.samples) for p in proofs),
            "samples_ok": sum(1 for p in proofs for s in p.samples
                              if s.status == 200),
        },
    }
    if extra:
        payload.update(extra)
    fp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                  encoding="utf-8")
    return fp
