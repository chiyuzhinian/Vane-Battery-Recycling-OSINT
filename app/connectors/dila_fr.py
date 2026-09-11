"""法国 DILA 开放数据连接器 —— Légifrance 的原始数据源（日增量）。

为什么走 DILA 而不是 Légifrance
-------------------------------
实测（2026-09-11）：
    legifrance.gouv.fr          → Cloudflare 挑战，有头 45s 也过不去 ❌
    echanges.dila.gouv.fr       → 200 ✅ **Légifrance 的原始数据源，完全开放**

⭐ 关键认知：**对监测系统来说，日增量才是对的产物，不是全量转储。**

    全量 LEGI 包   Freemium_legi_global_*.tar.gz  → **1.17 GB** ❌ 不实用
    日增量包       LEGI_YYYYMMDD-HHMMSS.tar.gz    → **0.9 ~ 1.8 MB** ✅

    监测要回答的是"**今天改了什么**"，不是"历史上全部是什么"。
    一开始按"全量"思路评估，差点把可用的源判死。

可用数据集（40+ 个）
--------------------
    LEGI/  法律与法令整合库（法规被修订）
    JORF/  官方公报（**新法规发布**的地方）⭐
    KALI/  集体劳动协议
    CONSTIT/ 宪法
    BODACC/ 商事与破产公告
    CIRCULAIRES/ 部委通函
    ...

用法
----
    async with get_connector("dila_fr") as c:
        items = await c.fetch(latest=3, keywords=["batterie", "véhicule hors d'usage"])
"""

from __future__ import annotations

import io
import re
import tarfile
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

BASE = "https://echanges.dila.gouv.fr/OPENDATA"
_HREF_RE = re.compile(r'href="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

# 本领域关键词（法语）。用于从增量包里筛出相关文本。
KEYWORDS_FR: list[str] = [
    "batterie", "batteries", "accumulateur", "pile",
    "véhicule hors d'usage", "vehicule hors d'usage", "VHU",
    "dépollution", "recyclage", "recyclé", "filière REP",
    "responsabilité élargie", "déchet", "masse noire",
    "brovage", "broyeur", "métaux", "cobalt", "lithium",
]


class DilaFrConnector(BaseConnector):
    """法国 DILA 开放数据（LEGI / JORF 日增量）。"""

    source_id = "fr_dila"
    base_url = BASE
    timeout = 90.0

    async def list_files(self, dataset: str = "LEGI",
                         limit: int = 200) -> list[str]:
        """列出某数据集目录下的增量包（倒序，最新在前）。"""
        resp = await self._polite_get(f"{BASE}/{dataset}/")
        names = [h for h in _HREF_RE.findall(resp.text)
                 if h.endswith(".tar.gz") and not h.startswith("?")]
        return sorted(names, reverse=True)[:limit]

    async def fetch(self, dataset: str = "LEGI", latest: int = 1,
                    keywords: list[str] | None = None,
                    max_files_scanned: int = 4000,
                    **kwargs: Any) -> list[RawEvidence]:
        """抓最近几个增量包，抽出与关键词相关的文本片段。

        ⚠️ LEGI 用的是 DILA 自有 DTD，完整解析是过度工程。
           这里做的是**关键词命中即取片段**：对"今天有没有相关法规变动"
           这个问题足够，且对 DTD 变化鲁棒。
        """
        kws = [k.lower() for k in (keywords or KEYWORDS_FR)]
        files = await self.list_files(dataset, limit=max(latest, 1) * 2)
        if not files:
            raise ConnectorError(f"{self.source_id}: {dataset} 目录下没有找到增量包")

        out: list[RawEvidence] = []
        for name in files[:latest]:
            try:
                blob = await self._download(name)
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ {name} 下载失败：{type(exc).__name__}")
                continue
            hits = self._scan(blob, kws, max_files_scanned)
            print(f"    {name}（{len(blob) / 1024:.0f} KB）→ 命中 {len(hits)} 个文本")
            for h in hits:
                out.append(RawEvidence(
                    evidence_id="",
                    channel="connector",
                    source_id=self.source_id,
                    source_url=f"{BASE}/{dataset}/{name}",
                    source_title=f"[DILA {dataset}] {h['title']}",
                    publish_date=None,
                    raw_text=h["text"][:4000],
                    meta={
                        "country": "FR",
                        "region_hint": "EU-MemberState",
                        "dataset": dataset,
                        "archive": name,
                        "legi_file": h["file"],
                        "matched_terms": h["terms"],
                        "channel_note": "DILA 开放数据（Légifrance 原始源），日增量",
                    },
                ))
        return out

    async def _download(self, name: str) -> bytes:
        resp = await self._polite_get(f"{BASE}/LEGI/{name}")
        return resp.content

    def _scan(self, blob: bytes, kws: list[str],
              max_files: int) -> list[dict]:
        """在 tar.gz 里逐文件扫关键词，命中即返回（含命中的词）。"""
        hits: list[dict] = []
        try:
            tar = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
        except tarfile.TarError as exc:
            raise ConnectorError(f"{self.source_id}: 归档损坏（{exc}）") from exc

        scanned = 0
        for member in tar:
            if not member.isfile() or not member.name.lower().endswith(".xml"):
                continue
            scanned += 1
            if scanned > max_files:
                break
            try:
                raw = tar.extractfile(member)
                if raw is None:
                    continue
                content = raw.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                continue
            low = content.lower()
            matched = [k for k in kws if k in low]
            if not matched:
                continue
            text = _WS_RE.sub(" ", _TAG_RE.sub(" ", content)).strip()
            title = self._title(content, member.name)
            hits.append({"file": member.name, "title": title,
                         "text": text, "terms": matched[:6]})
        return hits

    @staticmethod
    def _title(content: str, fallback: str) -> str:
        """尽量取法条标题；取不到就用文件名。"""
        for pat in (r"<TITRE_TXT[^>]*>(.*?)</TITRE_TXT>",
                    r"<TITRE[^>]*>(.*?)</TITRE>",
                    r"<NUM[^>]*>(.*?)</NUM>"):
            m = re.search(pat, content, re.S | re.I)
            if m:
                t = _WS_RE.sub(" ", _TAG_RE.sub("", m.group(1))).strip()
                if t:
                    return t[:120]
        return fallback

    async def probe(self) -> ProbeResult:
        import time
        t0 = time.monotonic()
        try:
            files = await self.list_files("LEGI", limit=50)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=f"{type(exc).__name__}")
        return ProbeResult(
            source_id=self.source_id, reachable=True, status_code=200,
            latency_ms=int((time.monotonic() - t0) * 1000),
            records_found=len(files),
            sample=files[:3])
