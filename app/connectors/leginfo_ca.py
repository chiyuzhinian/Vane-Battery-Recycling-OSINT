# -*- coding: utf-8 -*-
"""US-CA leginfo（leginfo.legislature.ca.gov）连接器 —— 加州官方立法信息。

Source Proof（2026-09-13，outputs/audit/source_proofs/US-CA.json）：
    · AB-2440 全文 + 状态页（200，标题 "Bill Text - AB-2440 …"）✅
    · PRC § 42451 条款页（AB 2440 编入 Public Resources Code）✅
    · 检索表单为 JS（billSearchClient）→ 采集走**已知文书直链**（DEFAULT_DOCS）

用法：
    async with LeginfoCaConnector() as c:
        items = await c.fetch()          # 默认：AB240 文本/状态 + 2 个条款
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ConnectorError, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html, trim_nav

MAX_TEXT = 60000
MIN_TEXT = 1500


class LeginfoCaConnector(BaseConnector):
    source_id = "us_ca_leginfo"
    base_url = "https://leginfo.legislature.ca.gov"
    timeout = 45.0

    #: (路径, 标题, doc_key, evidence_id)——显式 eid：status 尾缀按法案命名，
    #: 防跨法案冲突（AB2440 status 保留历史 eid `us_ca_leginfo_status`）
    DEFAULT_DOCS: list[tuple[str, str, str, str]] = [
        ("/faces/billTextClient.xhtml?bill_id=202120220AB2440",
         "AB 2440 — Responsible Battery Recycling Act of 2022（全文）",
         "US-CA:AB:2021-2022:AB2440", "us_ca_leginfo_ab2440"),
        ("/faces/billStatusClient.xhtml?bill_id=202120220AB2440",
         "AB 2440 — 立法状态（Chaptered）",
         "US-CA:AB:2021-2022:AB2440:status", "us_ca_leginfo_status"),
        ("/faces/codes_displaySection.xhtml?lawCode=PRC&sectionNum=42451",
         "California PRC § 42451（电池回收计划条款）",
         "US-CA:PRC:42451", "us_ca_leginfo_42451"),
        ("/faces/codes_displaySection.xhtml?lawCode=PRC&sectionNum=42452",
         "California PRC § 42452（电池回收计划条款）",
         "US-CA:PRC:42452", "us_ca_leginfo_42452"),
        # Step 7（2B0）：EV traction battery 专项 —— A1 核心对象（标题级）
        ("/faces/billTextClient.xhtml?bill_id=202520260SB615",
         "SB 615 — Vehicle traction batteries（全文）",
         "US-CA:SB:2025-2026:SB615", "us_ca_leginfo_sb615"),
        ("/faces/billStatusClient.xhtml?bill_id=202520260SB615",
         "SB 615 — 立法状态",
         "US-CA:SB:2025-2026:SB615:status", "us_ca_leginfo_sb615_status"),
    ]

    def doc_url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = [d for d in self.DEFAULT_DOCS
                   if not docs or d[2] in docs or d[1] in docs]
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for path, label, doc_key, eid in targets:
            url = self.doc_url(path)
            try:
                resp = await self._polite_get(url, headers={"User-Agent": BROWSER_UA})
                html = resp.text
                if detect_challenge(html):
                    raise ConnectorError("challenge_page")
                text = strip_html(html)
                if len(text) < MIN_TEXT:
                    raise ConnectorError(f"正文不足（{len(text)} 字符）")
                body, nav_removed = trim_nav(text)
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": doc_key, "error": type(exc).__name__})
                print(f"    ⚠️ us_ca_leginfo {doc_key} 失败：{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=eid,
                channel="connector", source_id=self.source_id,
                source_url=url, source_title=label, publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "US", "jurisdiction": "US-CA",
                      "doc_key": doc_key,
                      "page_title": extract_title(html),
                      "nav_trimmed_chars": nav_removed,
                      "collector": "LeginfoCaConnector",
                      "official_domain": "leginfo.legislature.ca.gov",
                      "language": "en",
                      "source_role": ("STATE_STATUTES" if "PRC" in doc_key
                                      else "STATE_LEGISLATURE")},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        url = self.doc_url(self.DEFAULT_DOCS[0][0])
        try:
            resp = await self._polite_get(url, headers={"User-Agent": BROWSER_UA})
            ok = resp.status_code == 200 and len(resp.content) > 5000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0, sample=[url])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
