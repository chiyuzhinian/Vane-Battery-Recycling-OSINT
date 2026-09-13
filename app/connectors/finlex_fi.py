# -*- coding: utf-8 -*-
"""FI Finlex（finlex.fi）连接器 —— 芬兰官方立法库。

Source Proof（2026-09-13，outputs/audit/source_proofs/FI.json）：
    · /fi/laki/ajantasa/{year}/{number} 直链可读（样本 3/3：Jätelaki 等）
    · 检索接口（fi/haku）未过主题核验 → 采集走**已知文书直链**（DEFAULT_DOCS）

用法：
    async with FinlexFiConnector() as c:
        items = await c.fetch()                    # 默认三部核心法
"""
from __future__ import annotations

from typing import Any

from .base import BROWSER_UA, BaseConnector, ConnectorError, ProbeResult, RawEvidence
from .leg_utils import (detect_challenge, extract_next_flight, extract_text_nodes,
                        extract_title, strip_html, trim_nav)

MAX_TEXT = 60000
#: 正文下限：低于此值视为 JS 壳/网络异常（Finlex 页面实测壳 1.5k）
MIN_TEXT = 2000


class FinlexFiConnector(BaseConnector):
    source_id = "fi_finlex"
    base_url = "https://www.finlex.fi"
    timeout = 45.0

    #: 年份 → (编号, 标题)；直链经 Source Proof 实抓验证
    DEFAULT_DOCS: dict[str, tuple[str, str]] = {
        "20110646": ("Jätelaki (646/2011)", "2011"),
        "20140527": ("Ympäristönsuojelulaki (527/2014)", "2014"),
        "20210978": ("Valtioneuvoston asetus jätteistä (978/2021)", "2021"),
    }

    def doc_url(self, number: str) -> str:
        year = number[:4]
        return f"{self.base_url}/fi/laki/ajantasa/{year}/{number}"

    async def fetch(self, docs: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        targets = docs or list(self.DEFAULT_DOCS)
        out: list[RawEvidence] = []
        self.last_errors: list[dict] = []
        for number in targets:
            try:
                resp = await self._polite_get(self.doc_url(number),
                                              headers={"User-Agent": BROWSER_UA})
                html = resp.text
                if detect_challenge(html):
                    raise ConnectorError("challenge_page")
                # Finlex 为 React 流式渲染：法条文本/标题在 __next_f 载荷的 
                # "text":"…" 节点中（实测 1042 节点/2.8 万字符；含电池条款）
                flight = extract_next_flight(html)
                nodes = extract_text_nodes(flight) if flight else ""
                if len(nodes) >= MIN_TEXT:
                    text = nodes
                elif flight:
                    text = strip_html(flight)
                else:
                    text = strip_html(html)
                if len(text) < MIN_TEXT:
                    raise ConnectorError(f"正文不足（{len(text)} 字符，疑 JS 壳/网络异常）")
            except Exception as exc:  # noqa: BLE001
                self.last_errors.append({"doc": number, "error": type(exc).__name__})
                print(f"    ⚠️ fi_finlex {number} 失败：{type(exc).__name__}")
                continue
            title = extract_title(html)
            fallback = self.DEFAULT_DOCS.get(number, (number, ""))[0]
            body, nav_removed = trim_nav(text)
            out.append(RawEvidence(
                evidence_id=f"fi_finlex_{number}",
                channel="connector", source_id=self.source_id,
                source_url=self.doc_url(number),
                source_title=fallback,
                publish_date=None,
                raw_text=body[:MAX_TEXT],
                meta={"region": "EU", "jurisdiction": "FI",
                      "doc_key": f"FI:SDK:{number[:4]}/{number[4:]}",
                      "page_title": title,
                      "nav_trimmed_chars": nav_removed,
                      "collector": "FinlexFiConnector",
                      "official_domain": "finlex.fi",
                      "language": "fi",
                      "source_role": "MS_LEGISLATION_DATABASE"},
            ))
        return out

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            resp = await self._polite_get(self.doc_url("20110646"))
            ok = resp.status_code == 200 and len(resp.content) > 1000
            return ProbeResult(self.source_id, ok, resp.status_code,
                               int((time.monotonic() - t0) * 1000),
                               1 if ok else 0)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(self.source_id, False, None,
                               int((time.monotonic() - t0) * 1000), 0,
                               error=type(exc).__name__)
