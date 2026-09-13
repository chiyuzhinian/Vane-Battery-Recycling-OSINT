# -*- coding: utf-8 -*-
"""PL Sejm ELI API 连接器 —— 波兰官方法律 API（替代被 Distil 挡的 ISAP）。

Step 5 探测（2026-09-13）：
    · GET https://api.sejm.gov.pl/eli/acts/DU/{year}/{pos}       → 元数据 JSON
    · GET https://api.sejm.gov.pl/eli/acts/DU/{year}/{pos}/text.html → 全文 HTML
    · references."Akty wykonawcze" = 实施法案家族（C 路线种子）
    · isap.sejm.gov.pl 直链仍被 Distil 拦截 → 本通道为**官方替代端点**，
      不绕过访问控制（走官方公开 API）

用法：
    async with SejmEliPlConnector() as c:
        items = await c.fetch()                        # 默认 3 部核心
        items = await c.fetch(docs=["2009/666"])
"""
from __future__ import annotations

import re
from typing import Any

from .base import BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, strip_html, trim_nav

MAX_TEXT = 200_000
MIN_TEXT = 1500

API = "https://api.sejm.gov.pl/eli/acts"
DEFAULT_DOCS = ["2009/666", "2021/1256", "2019/813"]


class SejmEliPlConnector(BaseConnector):
    source_id = "pl_sejm_eli"
    base_url = "https://api.sejm.gov.pl"
    timeout = 60.0

    def doc_url(self, doc: str) -> str:
        return f"{API}/DU/{doc}"

    def text_url(self, doc: str) -> str:
        return f"{API}/DU/{doc}/text.html"

    async def _fetch_meta(self, doc: str) -> dict:
        resp = await self._polite_get(self.doc_url(doc))
        return resp.json()

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        """docs 可传 'YYYY/POS'；expand_related=True 时并入实施法案家族。"""
        expand = bool(kwargs.get("expand_related", False))
        targets = list(docs or DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for doc in targets:
            try:
                resp = await self._polite_get(self.text_url(doc))
                html = resp.text
                meta = {}
                try:
                    meta = await self._fetch_meta(doc)
                except Exception:  # noqa: BLE001 —— 元数据失败不阻断全文
                    pass
                if detect_challenge(html):
                    raise RuntimeError("challenge_page")
                body, nav = trim_nav(strip_html(html))
                if len(body) < MIN_TEXT:
                    raise RuntimeError(f"text_too_short({len(body)})")
                year, pos = doc.split("/", 1)
                title = str(meta.get("title") or f"DU {doc}")
                out.append(RawEvidence(
                    evidence_id=f"pl_sejm_eli_{year}_{pos}",
                    channel="connector", source_id=self.source_id,
                    source_url=self.doc_url(doc),
                    source_title=title[:200], publish_date=None,
                    raw_text=body[:MAX_TEXT],
                    meta={"region": "EU", "jurisdiction": "PL",
                          "doc_key": f"PL:ELI:DU/{doc}",
                          "eli": str(meta.get("ELI") or ""),
                          "legal_status": str(meta.get("status") or ""),
                          "announcement_date": str(
                              meta.get("announcementDate") or ""),
                          "effective_from": str(meta.get("validFrom") or ""),
                          "nav_trimmed_chars": nav,
                          "collector": "SejmEliPlConnector",
                          "official_domain": "api.sejm.gov.pl",
                          "language": "pl",
                          "source_role": "MS_LEGISLATION_DATABASE"},
                ))
                if expand:
                    for ref in ((meta.get("references") or {})
                                .get("Akty wykonawcze") or [])[:8]:
                        rid = str(ref.get("id") or "")          # "DU/2019/813"
                        m = re.match(r"DU/(\d{4})/(\d+)$", rid)
                        if m:
                            cand = f"{m.group(1)}/{m.group(2)}"
                            if cand not in targets:
                                targets.append(cand)
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": doc,
                                         "error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:120]})
                print(f"    ⚠️ pl_sejm_eli {doc} 失败：{type(exc).__name__}")
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.text_url("2009/666"))
            ok = resp.status_code == 200 and len(resp.content) > 5000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0, sample=[self.text_url("2009/666")])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
