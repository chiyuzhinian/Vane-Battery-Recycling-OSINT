# -*- coding: utf-8 -*-
"""SE SFST（rkrattsbaser.gov.se）连接器 —— 瑞典官方法典库。

Source Proof（2026-09-13，outputs/audit/source_proofs/SE.json）：
    · 入口 + 文书直链（?bet=YYYY:NNN）可读，全文/元数据成立（样本 3/3）
    · fritext 检索未过主题核验 → 采集走**已知文书直链**（DEFAULT_DOCS）

用法：
    async with SfstSeConnector() as c:
        items = await c.fetch()                       # 默认三部核心法
        items = await c.fetch(docs=["2020:614"])
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .base import BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, extract_title, strip_html, trim_nav

MAX_TEXT = 60000


class SfstSeConnector(BaseConnector):
    source_id = "se_sfst"
    base_url = "https://rkrattsbaser.gov.se"
    timeout = 45.0

    #: SFS 编号 → 标题（编号经 Source Proof 实抓验证）
    DEFAULT_DOCS: dict[str, str] = {
        "2008:834": "Förordning (2008:834) om producentansvar för batterier",
        "2007:185": "Förordning (2007:185) om producentansvar för bilar",
        "2020:614": "Avfallsförordning (2020:614)",
    }

    def doc_url(self, sfs: str) -> str:
        return f"{self.base_url}/sfst?bet={sfs}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = docs or list(self.DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for sfs in targets:
            try:
                resp = await self._polite_get(self.doc_url(sfs))
            except Exception as exc:  # noqa: BLE001 —— 单篇失败不中断
                self.last_errors.append({"doc": sfs, "error": type(exc).__name__})
                print(f"    ⚠️ se_sfst {sfs} 失败：{type(exc).__name__}")
                continue
            html = resp.text
            if detect_challenge(html):
                self.last_errors.append({"doc": sfs, "error": "challenge_page"})
                continue
            page_title = extract_title(html)
            fallback = self.DEFAULT_DOCS.get(sfs, sfs)
            body, nav_removed = trim_nav(strip_html(html))
            out.append(RawEvidence(
                evidence_id=f"se_sfst_{sfs.replace(':', '_')}",
                channel="connector", source_id=self.source_id,
                source_url=self.doc_url(sfs),
                source_title=f"SFS {sfs} — {fallback}",
                publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "EU", "jurisdiction": "SE",
                      "doc_key": f"SE:SFS:{sfs}",
                      "page_title": page_title,
                      "nav_trimmed_chars": nav_removed,
                      "collector": "SfstSeConnector",
                      "official_domain": "rkrattsbaser.gov.se",
                      "language": "sv",
                      "source_role": "MS_LEGISLATION_DATABASE"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url("2008:834"))
            ok = resp.status_code == 200 and len(resp.content) > 1000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0,
                               sample=[self.doc_url("2008:834")])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
