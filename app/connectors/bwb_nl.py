"""荷兰法规连接器 —— KOOP 官方 BWB（Basiswettenbestand）通道。

为什么荷兰此前被判为"不可用"
----------------------------
`wetten.overheid.nl` 可达（200），但搜索页是 **JS 表单**，HTML 里一个 BWB 编号都没有。
于是结论是"需要 BWB 编号才行"—— 但**编号从哪来**一直没解决。

实测定论（2026-09-11）：编号有现成的检索 API，只是参数名反直觉
------------------------------------------------------------
① 检索入口：`https://zoekservice.overheid.nl/sru/Search`（SRU 2.0 协议）
   · 连接名必须是 **`BWB`**（大写）。试过 Wetten/wetten/Wet/Regelgeving/
     Kamerstukken/Staatscourant/Bladen/Tractatenblad/OfficielePublicaties/
     officielebekendmakingen/"Wet- en regelgeving" —— **全部 "Unsupported parameter value"**。
     唯独 `BWB` 通过了连接名校验（说明这个连接是真实存在的）。
   · 版本参数名是 **`version`**，不是 `x-version`。
     传 `x-version=1.2` → 仍报 "Mandatory parameter not supplied: version"；
     传 `version=1.1` → "Unsupported version (支持 1.2,2.0)"；
     传 **`version=1.2`** → 通过。⚠️ 两个参数名只差一个 `x-`，卡了很久。
   · 索引名**不能猜**。`title` / `dc.title` / `dcterms.title` / `all` / `text` /
     `bwbtitel` / `overheidbwb.bwbtitel` 全是 "Unsupported index"。
     正解是问 `operation=explain` 要清单，它返回 **14 个索引**（权威）：
        dcterms:identifier / modified / type
        overheid:authority
        overheidbwb:titel / afkorting / rechtsgebied / overheidsdomein /
                    wetsfamilie / geldigheidsdatum / zichtdatum / bekendmaking /
                    dossiernummer / onderwerpVerdrag
     CQL 里写作 `overheidbwb.titel=xxx`（点号，不是冒号）。

② 全文入口：`https://repository.officiele-overheidspublicaties.nl/bwb/<BWB编号>`
   · 返回官方 **XML**（Wet milieubeheer = 137 KB），**不需要解析 6 MB 的网页 HTML**
     （`wetten.overheid.nl/BWBR0003245` 也有全文，但 6.1 MB 且是 HTML）。
   · SRU 记录里更直接给了版本级直链 `overheidbwb:locatie_toestand`。

⭐ 索引是**精确词匹配，不做词干还原**
--------------------------------
    overheidbwb.titel=autowrak   → 0 条
    overheidbwb.titel=autowrakken→ 44 条
荷兰语大量复合词，**必须逐词形检索**（正确写法是 autowrakken，不是 autowrak）。

实测命中
--------
    titel=autowrakken    →  44      titel=afvalstoffen  → 251
    titel=batterijen     →  29      rechtsgebied=milieurecht → 8220
    afkorting=Wm         → 196（Wet milieubeheer 的 196 个历史版本）
    dcterms.modified=2026-09-01 → 72  ← ⭐ 增量监测通道成立

⭐ 版本即记录：同一部法的每个历史版本是独立记录
--------------------------------------------
`BWBR0024492` 在结果里出现 13 次 = 13 个版本，各带
`geldigheidsperiode_startdatum/einddatum`。
→ 取 startdatum 最大的版本 = **当前有效文本**；
→ 全部版本 = **该法的变更时间线**（与欧盟侧的 14 次更正同一思路）。

用法
----
    async with get_connector("nl_bwb") as c:
        items = await c.fetch(terms=["autowrakken", "batterijen"])
        items = await c.fetch(bwb_ids=["BWBR0013707"])
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


class BwbNlConnector(BaseConnector):
    """荷兰国家法规（KOOP BWB 官方 XML）。"""

    source_id = "nl_bwb"
    base_url = "https://zoekservice.overheid.nl"
    timeout = 60.0

    SRU = "https://zoekservice.overheid.nl/sru/Search"
    REPO = "https://repository.officiele-overheidspublicaties.nl/bwb"

    # SRU 连接名与版本 —— 两个参数名都反直觉，见模块 docstring
    CONNECTION = "BWB"
    VERSION = "1.2"

    # 检索词：**荷兰语词形**（索引不做词干还原，autowrak 查不到 autowrakken）
    DEFAULT_TERMS: tuple[str, ...] = (
        "autowrakken",       # 报废车辆（ELV）
        "batterijen",        # 电池
        "accumulatoren",     # 蓄电池
        "afvalstoffen",      # 废物（黑粉定性依据）
        "afvalbeheer",
        "autobanden",
    )

    # 正文里我们关心的荷兰语术语
    KEY_TERMS: tuple[str, ...] = (
        "autowrak", "batterij", "accumulator", "afvalstof", "gevaarlijk",
        "recycling", "inzameling", "verwijdering", "nuttige toepassing",
        "producentenverantwoordelijkheid", "zwarte massa", "schredder",
        "demonteren", "cobalt", "lithium", "nikkel",
    )

    def __init__(self, client: Any = None) -> None:
        super().__init__(client=client)
        self._cache: dict[str, list[dict]] = {}

    # ---------- SRU 检索 ----------
    async def search(self, term: str, limit: int = 60, start: int = 1) -> list[dict]:
        """按标题词检索法规，返回该词的**全部版本记录**。

        ⚠️ 索引是精确词匹配：查 `autowrak` 得 0 条，`autowrakken` 得 44 条。
        """
        key = f"{term}|{limit}|{start}"
        if key in self._cache:
            return self._cache[key]

        resp = await self._polite_get(
            self.SRU,
            params={
                "x-connection": self.CONNECTION,
                "version": self.VERSION,
                "operation": "searchRetrieve",
                "query": f"overheidbwb.titel={term}",
                "maximumRecords": str(limit),
                "startRecord": str(start),
            },
        )
        xml = resp.text
        if "diagnostic" in xml:
            m = re.search(r"<message>([^<]+)</message>", xml)
            raise ConnectorError(f"{self.source_id}: SRU 拒绝查询（{m.group(1) if m else '?'}）")

        records = [_parse_record(r) for r in re.findall(r"<record>(.*?)</record>", xml, re.S)]
        records = [r for r in records if r.get("bwb_id")]
        self._cache[key] = records
        return records

    async def search_many(self, terms: list[str], per_term: int = 60) -> list[dict]:
        """多词检索并合并（按 BWB 编号去重，保留全部版本）。"""
        seen: dict[str, dict] = {}
        for term in terms:
            try:
                for rec in await self.search(term, limit=per_term):
                    key = f"{rec['bwb_id']}|{rec.get('start')}"
                    if key not in seen:
                        rec["matched_term"] = term
                        seen[key] = rec
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ nl_bwb 检索 {term} 失败：{type(exc).__name__}")
        return list(seen.values())

    async def modified_since(self, date: str, limit: int = 100) -> list[dict]:
        """增量通道：某日之后被修改的法规（`dcterms.modified`）。

        与法国 DILA 日增量同一思路 —— 监测要回答"今天改了什么"。
        """
        resp = await self._polite_get(
            self.SRU,
            params={
                "x-connection": self.CONNECTION,
                "version": self.VERSION,
                "operation": "searchRetrieve",
                "query": f"dcterms.modified={date}",
                "maximumRecords": str(limit),
            },
        )
        return [
            _parse_record(r) for r in re.findall(r"<record>(.*?)</record>", resp.text, re.S)
        ]

    # ---------- 抓取正文 ----------
    async def fetch(self, bwb_ids: list[str] | None = None,
                    terms: list[str] | None = None,
                    limit: int | None = None,
                    **kwargs: Any) -> list[RawEvidence]:
        """抓取指定法规正文。

        · bwb_ids 优先（直接按编号取）
        · 否则按 terms 检索（默认 DEFAULT_TERMS）
        · 每部法只取**当前有效版本**（startdatum 最大者）
        """
        if bwb_ids:
            grouped: dict[str, list[dict]] = {b: [{"bwb_id": b}] for b in bwb_ids}
        else:
            records = await self.search_many(list(terms or self.DEFAULT_TERMS))
            grouped = {}
            for rec in records:
                grouped.setdefault(rec["bwb_id"], []).append(rec)

        out: list[RawEvidence] = []
        for bwb_id, versions in grouped.items():
            try:
                out.append(await self._fetch_one(bwb_id, versions))
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ nl_bwb {bwb_id} 失败：{type(exc).__name__}: {exc}")
            if limit and len(out) >= limit:
                break
        return out

    async def _fetch_one(self, bwb_id: str, versions: list[dict]) -> RawEvidence:
        # 当前有效版本 = geldigheidsperiode_startdatum 最大者
        # ⚠️ 必须先按 BWB 编号过滤：SRU 一次返回多部法，不过滤会取到别部的版本
        versions = [v for v in versions if v.get("start") and v.get("bwb_id") == bwb_id]
        current = max(versions, key=lambda v: v["start"]) if versions else {}
        title = current.get("title") or bwb_id

        # ⚠️ 必须用**版本级** XML（locatie_toestand）。
        #    作品级 `{REPO}/{bwb_id}` 只有 <work> 元数据（WTI），**一个字法条都没有**：
        #      BWBR0013707 作品级 6,090 字符，`autowrak` 出现 0 次
        #      BWBR0013707 版本级 20,191 字符，`autowrak` 出现 26 次
        #    拿作品级入管会得到一个“采集成功但内容为空壳”的记录。
        url = current.get("xml_url")
        if not url:
            raise ConnectorError(
                f"{self.source_id}: {bwb_id} 缺 locatie_toestand，"
                "无法定位版本级 XML（作品级 XML 不含法条正文，不可用）")

        resp = await self._polite_get(url)
        text, meta = self._parse_xml(resp.content)

        return RawEvidence(
            evidence_id="",
            channel="connector",
            source_id=self.source_id,
            # source_url = **实际取证的版本级 XML**（存证要指向真正拿到的那个文件）
            source_url=url,
            source_title=f"{title} [{bwb_id}] {current.get('start') or ''}".strip(),
            publish_date=_parse_date(current.get("start") or current.get("modified")),
            raw_text=text,
            meta={
                "bwb_id": bwb_id,
                "country": "NL",
                "region_hint": "EU-MemberState",
                "cluster_hint": "C2_elv",
                "law_title": title,
                "law_type": current.get("type"),
                "authority": current.get("authority"),
                "rechtsgebied": current.get("rechtsgebied"),
                "version_start": current.get("start"),
                "version_end": current.get("end"),
                "modified": current.get("modified"),
                # ⭐ 版本时间线：同一部法的全部历史版本
                "version_count": len(versions),
                "version_timeline": [
                    {"start": v.get("start"), "end": v.get("end")}
                    for v in sorted(versions, key=lambda v: v.get("start") or "")
                ][-25:],
                "matched_term": current.get("matched_term"),
                "xml_url": url,
                "work_url": f"{self.REPO}/{bwb_id}",
                "xml_root": meta.get("root"),
                "term_hits": meta.get("term_hits"),
                "channel_note": "KOOP BWB 官方版本级 XML（repository.officiele-overheidspublicaties.nl）",
            },
        )

    # ---------- 解析 ----------
    def _parse_xml(self, blob: bytes) -> tuple[str, dict]:
        """官方 XML → 纯文本。

        不做完整 LegalDocML 解析：块级标签转换行、行内标签去掉，
        对"能否搜到内容"足够，且对结构变化更鲁棒（同德国连接器的取舍）。
        """
        raw = blob.decode("utf-8", "replace")
        if not raw.strip():
            raise ConnectorError(f"{self.source_id}: 空响应")

        # ⚠️ 防“取到错文件”：作品级 <work> 是 WTI 元数据，**不含法条**。
        #    若上游 locatie_toestand 缺失而回退到作品级，这里必须报错而不是默默入库。
        root_m = re.match(r"\s*<\?xml[^>]*\?>\s*<([A-Za-z]+)", raw)
        root = root_m.group(1) if root_m else "?"
        if root == "work":
            raise ConnectorError(
                f"{self.source_id}: 取到 <work> 作品级元数据（WTI），不含法条正文；"
                "必须用 SRU 记录里的 locatie_toestand（版本级 XML）")

        txt = re.sub(r"</(al|lid|artikel|afdeling|hoofdstuk|paragraaf|bijlage|titel|kop|div)>",
                     "\n", raw, flags=re.I)
        txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
        txt = _TAG_RE.sub("", txt)
        txt = (txt.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
                  .replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'"))
        txt = _WS_RE.sub(" ", txt)
        txt = _BLANK_RE.sub("\n\n", txt).strip()

        hits = {t: len(re.findall(re.escape(t), txt, re.I)) for t in self.KEY_TERMS}
        hits = {k: v for k, v in sorted(hits.items(), key=lambda kv: -kv[1]) if v}
        return txt, {"root": root, "term_hits": hits}

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        t0 = time.monotonic()
        try:
            recs = await self.search("autowrakken", limit=5)
        except Exception as exc:  # noqa: BLE001
            return ProbeResult(
                source_id=self.source_id, reachable=False, status_code=None,
                latency_ms=int((time.monotonic() - t0) * 1000), records_found=0,
                error=f"{type(exc).__name__}: {exc}")

        sample = [f"{r['bwb_id']} {r.get('title', '')[:44]}" for r in recs[:3]]
        ok = 0
        if recs:
            try:
                # ⚠️ 必须只传同一 BWB 编号的版本，否则会串到另一部法的版本上
                same = [r for r in recs if r["bwb_id"] == recs[0]["bwb_id"]]
                it = await self._fetch_one(recs[0]["bwb_id"], same)
                ok = len(it.raw_text)
                sample.append(f"正文 {ok} 字符（{it.meta.get('version_start')} 版本，"
                              f"共 {it.meta.get('version_count')} 个版本）")
            except Exception as exc:  # noqa: BLE001
                sample.append(f"正文失败：{type(exc).__name__}: {exc}")
        return ProbeResult(
            source_id=self.source_id,
            reachable=True,
            status_code=200,
            latency_ms=int((time.monotonic() - t0) * 1000),
            records_found=len(recs),
            sample=sample,
            error=None if ok else "检索可用但正文拉取失败",
        )


# ---------- 记录解析 ----------
def _tag(xml: str, name: str) -> str | None:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", xml, re.S)
    if not m:
        return None
    return _WS_RE.sub(" ", re.sub(r"\s+", " ", m.group(1))).strip()


def _all_tags(xml: str, name: str) -> list[str]:
    return [_WS_RE.sub(" ", m).strip()
            for m in re.findall(rf"<{name}[^>]*>(.*?)</{name}>", xml, re.S)]


def _parse_record(block: str) -> dict:
    """把一条 SRU 记录解析成扁平 dict。"""
    return {
        "bwb_id": _tag(block, "dcterms:identifier"),
        "title": _tag(block, "dcterms:title"),
        "type": _tag(block, "dcterms:type"),
        "authority": _tag(block, "overheid:authority"),
        "modified": _tag(block, "dcterms:modified"),
        "created": _tag(block, "dcterms:created"),
        "rechtsgebied": next(iter(_all_tags(block, "overheidbwb:rechtsgebied")), None),
        "start": _tag(block, "overheidbwb:geldigheidsperiode_startdatum"),
        "end": _tag(block, "overheidbwb:geldigheidsperiode_einddatum"),
        "xml_url": _tag(block, "overheidbwb:locatie_toestand"),
        "manifest": _tag(block, "overheidbwb:locatie_manifest"),
    }


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
