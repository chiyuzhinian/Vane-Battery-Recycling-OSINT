"""德国联邦法律门户（gesetze-im-internet.de）连接器 —— 官方 XML。

为什么德国要走 XML 而不是抓网页
--------------------------------
实测（2026-09-11）：
  · HTML 页面 `https://www.gesetze-im-internet.de/<slug>/`
      → 只有 524~4629 字符，是 **"nichtamtliches Inhaltsverzeichnis"（目录）**，不是正文
  · 官方 XML 包 `https://www.gesetze-im-internet.de/<slug>/xml.zip`
      → HTTP 200 / application/zip，**完整法条正文 + 修订历史**

实测内容（纯文本长度）：
    altautov（AltfahrzeugV 报废车）      54,439 字符   Altfahrzeug ×86
    battdg  （BattDG 电池法）            127,617 字符   Batterie ×319
    avv     （AVV 欧洲废物目录）          77,588 字符   gefährlich ×183  ← 危废分类

⭐ 这是"成员国层"的正确打开方式：**官方结构化数据 > 网页抓取**。
   同为成员国层的法国 ADEME 还需抓页面（因为它是 JS 门户），德国直接给 XML。

顺带解决了一个找 URL 的难题
---------------------------
`AltfahrzeugV` 的 slug **不是** `altfahrzeugv`，而是 `altautov`
（缩写来自旧称 Altauto-Verordnung）。猜了 4 个 slug 全 404。
正解：站点提供全量目录 `gii-toc.xml`（6130 部法规）→ 搜标题拿 slug。
**猜 URL 是低效的，先找目录/清单才是对的。**

用法
----
    async with get_connector("de_gesetze") as c:
        items = await c.fetch(terms=["Altfahrzeug", "Batterie", "gefährlich"])
        # slug 也可直接指定：
        items = await c.fetch(slugs=["altautov", "battdg", "avv"])
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from datetime import datetime, timezone
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


class GesetzeDeConnector(BaseConnector):
    """德国联邦法律与法令（官方 XML）。"""

    source_id = "de_gesetze"
    base_url = "https://www.gesetze-im-internet.de"
    timeout = 60.0

    CATALOG_URL = "https://www.gesetze-im-internet.de/gii-toc.xml"

    # 与电池/报废车/黑粉直接相关的德国核心法规。
    # slug 全部经实测验证（HTML 与 XML 双通），不要凭名字猜。
    DEFAULT_LAWS: dict[str, str] = {
        "altautov": "AltfahrzeugV —— 报废车移交、回收与无害化处置条例"
                    "（德国转化 ELV 指令 2000/53/EC 的国内法）",
        "battdg": "BattDG —— 电池法（实施欧盟条例 (EU) 2023/1542）",
        "avv": "AVV —— 欧洲废物目录条例（含危险废物分类，黑粉定性的德国依据）",
        "eag-behandv": "EAG-BehandV —— 废弃电子电气设备处理要求条例",
        "abfbeauftrv_2017": "AbfBeauftrV —— 废物管理代表人条例",
    }

    # 法规正文里我们关心的德语术语
    KEY_TERMS: tuple[str, ...] = (
        "Altfahrzeug", "Batterie", "Altbatterie", "gefährlich", "Abfall",
        "Verwertung", "Recycling", "Rücknahme", "Schredder", "Verbringung",
        "Lithium", "Akkumulator", "Sammlung", "Quote",
    )

    def __init__(self, client: Any = None) -> None:
        super().__init__(client=client)
        self._catalog: dict[str, dict] | None = None

    # ---------- 目录（一次下载，全量法规）----------
    async def catalog(self) -> dict[str, dict]:
        """下载并解析全量法规目录（6130 部）。结果缓存在实例上。

        ⚠️ 必须先有目录再找法规：直接猜 slug 会 404
        （AltfahrzeugV 的真实 slug 是 `altautov`，与名字毫无相似之处）。
        """
        if self._catalog is not None:
            return self._catalog

        resp = await self._polite_get(self.CATALOG_URL)
        xml = resp.text
        out: dict[str, dict] = {}
        for item in re.findall(r"<item[^>]*>(.*?)</item>", xml, re.S):
            m_title = re.search(r"<title>(.*?)</title>", item, re.S)
            m_link = re.search(r"<link>(.*?)</link>", item, re.S)
            if not (m_title and m_link):
                continue
            title = _WS_RE.sub(" ", m_title.group(1)).strip()
            link = m_link.group(1).strip()
            m_slug = re.search(r"/([^/]+)/xml\.zip$", link)
            if not m_slug:
                continue
            out[m_slug.group(1)] = {"slug": m_slug.group(1), "title": title, "link": link}
        self._catalog = out
        return out

    async def search(self, terms: list[str]) -> list[dict]:
        """按德语术语在法规标题里检索，返回候选法规。

        注意：这是**标题**匹配，召回有限（很多法规标题不含"Batterie"）。
        要精确定位仍应靠关键词体系 + 已知 slug 清单。
        """
        cat = await self.catalog()
        pats = [re.compile(re.escape(t), re.I) for t in terms]
        hits = []
        for rec in cat.values():
            if any(p.search(rec["title"]) for p in pats):
                hits.append(rec)
        return hits

    # ---------- 抓取正文 ----------
    async def fetch(self, slugs: list[str] | None = None,
                    terms: list[str] | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        """抓取指定法规（或按术语检索出来的法规）的完整正文。

        slugs 优先；未给则用 terms 检索目录后取前若干部。
        """
        targets: list[dict] = []
        if slugs:
            cat = await self.catalog()
            for s in slugs:
                rec = cat.get(s)
                targets.append(rec or {"slug": s, "title": s})
        elif terms:
            found = await self.search(terms)
            targets = found[:12]          # 限量，避免一次拉几十个 zip
        else:
            cat = await self.catalog()
            targets = [cat[s] for s in self.DEFAULT_LAWS if s in cat]

        out: list[RawEvidence] = []
        for rec in targets:
            try:
                out.append(await self._fetch_one(rec))
            except Exception as exc:  # noqa: BLE001
                # 单部法规失败不应中断整批
                print(f"    ⚠️ {rec.get('slug')} 失败：{type(exc).__name__}")
        return out

    async def _fetch_one(self, rec: dict) -> RawEvidence:
        slug = rec["slug"]
        url = f"{self.base_url}/{slug}/xml.zip"
        resp = await self._polite_get(url)
        text, meta = self._parse_zip(resp.content)

        title = rec.get("title") or slug
        return RawEvidence(
            evidence_id="",                       # __post_init__ 会自动算
            channel="connector",
            source_id=self.source_id,
            source_url=f"{self.base_url}/{slug}/",
            source_title=f"{title} [{slug}]",
            publish_date=None,
            raw_text=text,
            meta={
                "slug": slug,
                "country": "DE",
                "region_hint": "EU-MemberState",
                "cluster_hint": "C2_elv",
                "xml_url": url,
                "law_title": title,
                "amendment": meta.get("amendment"),
                "cite": meta.get("cite"),
                "term_hits": meta.get("term_hits"),
                "channel_note": "官方 XML（gesetze-im-internet.de），非网页抓取",
            },
        )

    # ---------- 解析 ----------
    def _parse_zip(self, blob: bytes) -> tuple[str, dict]:
        """从 xml.zip 里取出正文纯文本 + 元信息。

        德国官方法条 XML 的结构：<dokumente><norm><text>…</text></norm>…
        这里不做完整 LegalDocML 解析（过度工程），而是
        ① 去标签 ② 保留段落换行 ③ 压掉多余空白。
        对"能不能搜到内容"这个目标足够，且对结构变化更鲁棒。
        """
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile as exc:
            raise ConnectorError(f"{self.source_id}: XML 包损坏（{exc}）") from exc

        xmls = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not xmls:
            raise ConnectorError(f"{self.source_id}: XML 包内无 .xml（{z.namelist()}）")

        raw = z.read(xmls[0]).decode("utf-8", "replace")

        # 元信息：BGBl 出处与修订说明
        cite = re.search(r"(BGBl[^<]{0,60})", raw)
        amend = re.search(r"(Geändert durch[^<]{0,120}|Zuletzt geändert durch[^<]{0,120})", raw)

        # 段落级去标签：块级标签转换行，行内标签直接去掉
        txt = re.sub(r"</(absatz|text|norm|ueberschrift|titel|inhalt)>", "\n", raw)
        txt = re.sub(r"<br\s*/?>", "\n", txt)
        txt = _TAG_RE.sub("", txt)
        txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&")
                  .replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"'))
        txt = _WS_RE.sub(" ", txt)
        txt = _BLANK_RE.sub("\n\n", txt).strip()

        hits = {t: len(re.findall(re.escape(t), txt, re.I)) for t in self.KEY_TERMS}
        hits = {k: v for k, v in sorted(hits.items(), key=lambda kv: -kv[1]) if v}
        return txt, {
            "cite": cite.group(1).strip() if cite else None,
            "amendment": amend.group(1).strip() if amend else None,
            "term_hits": hits,
        }

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        """回答"能不能搜到"：目录可下 + 默认法规可拉 + 正文非空。"""
        t0 = time.monotonic()
        try:
            cat = await self.catalog()
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=f"目录不可达：{type(exc).__name__}")
        sample = []
        ok = 0
        for slug in list(self.DEFAULT_LAWS)[:2]:
            try:
                it = await self._fetch_one({"slug": slug, "title": self.DEFAULT_LAWS[slug]})
                ok += 1
                sample.append(f"{slug}: {len(it.raw_text)} 字符")
            except Exception as exc:  # noqa: BLE001
                sample.append(f"{slug}: {type(exc).__name__}")
        return ProbeResult(
            source_id=self.source_id,
            reachable=True,
            status_code=200,
            latency_ms=int((time.monotonic() - t0) * 1000),
            records_found=len(cat),
            sample=sample,
            error=None if ok else "默认法规全部拉取失败",
        )
