# -*- coding: utf-8 -*-
"""US-KY KRS 连接器 —— 肯塔基修订版法规（apps.legislature.ky.gov）。

Step 5 探测（2026-09-13）：
    · /law/statutes/ 目录可达（110KB）；ch224 章节索引 269 条 statute 链接
    · /law/statutes/statute.aspx?id=NNNN 条文页（官方服务器渲染；部分 id 为 PDF）
    · KRS 编号从条文页标题提取（如 "224.46-012"）

用法：
    async with KrsKyConnector() as c:
        items = await c.fetch(docs=["10039", ...])      # statute id
"""
from __future__ import annotations

import re
from typing import Any

from .base import BaseConnector, ProbeResult, RawEvidence
from .leg_utils import detect_challenge, strip_html, trim_nav

MAX_TEXT = 60_000
MIN_TEXT = 400

BASE = "https://apps.legislature.ky.gov"
#: 经 Step 5 目录验证的 statute id（条文页）
DEFAULT_DOCS = ["10039", "10068", "9989"]

_KRS_RE = re.compile(r"(?:KRS\s+)?(\d{3}[A-Z]?\.\d{2,3}-\d{2,3}|\d{3}\.\d{2,3})")


class KrsKyConnector(BaseConnector):
    source_id = "us_ky_krs"
    base_url = BASE
    timeout = 45.0

    def doc_url(self, statute_id: str) -> str:
        return f"{BASE}/law/statutes/statute.aspx?id={statute_id}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = list(docs or DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for sid in targets:
            url = self.doc_url(sid)
            try:
                resp = await self._polite_get(url)
                html = resp.text
                if detect_challenge(html):
                    raise RuntimeError("challenge_page")
                body, nav = trim_nav(strip_html(html))
                if len(body) < MIN_TEXT:
                    raise RuntimeError(f"text_too_short({len(body)})")
                m = _KRS_RE.search(body[:400])
                krs = m.group(1) if m else f"id:{sid}"
                title = body[:150].strip()
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": sid,
                                         "error": f"{type(exc).__name__}: "
                                                  f"{exc}"[:120]})
                print(f"    ⚠️ us_ky_krs {sid} 失败：{type(exc).__name__}")
                continue
            out.append(RawEvidence(
                evidence_id=f"us_ky_krs_{sid}",
                channel="connector", source_id=self.source_id,
                source_url=url, source_title=title, publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "US", "jurisdiction": "US-KY",
                      "doc_key": f"US-KY:KRS:{krs}",
                      "statute_id": sid,
                      "nav_trimmed_chars": nav,
                      "collector": "KrsKyConnector",
                      "official_domain": "apps.legislature.ky.gov",
                      "language": "en",
                      "source_role": "STATE_STATUTES"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url(DEFAULT_DOCS[0]))
            ok = resp.status_code == 200 and len(resp.content) > 500
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0,
                               sample=[self.doc_url(DEFAULT_DOCS[0])])
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
