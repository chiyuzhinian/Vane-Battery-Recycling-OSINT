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
import html
import asyncio
import tarfile
from datetime import datetime, timezone
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence

BASE = "https://echanges.dila.gouv.fr/OPENDATA"
_HREF_RE = re.compile(r'href="([^"]+)"')
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# 增量包名形如 LEGI_20260911-003012.tar.gz / JORF_20260911-002839.tar.gz
_NAME_DATE_RE = re.compile(r"_(\d{8})-\d{6}\.tar\.gz$")

# ⭐ DILA XML 的**正文容器**（按优先级）。
#    实测 JORF 的 <BLOC_TEXTUEL> 内长 26,883 字符，LEGI 同构。
#
#    ⚠️ 不要把 <TEXTE> 放进来：在 JORF 里它是「所属文本的引用信息」
#       （cid / date_publi / nature），内长仅 412 字符，是**指针不是正文**。
#       把它当正文会让判定器又一次只看到元数据。
_BODY_TAGS = ("BLOC_TEXTUEL", "CONTENU")
# 剥标签兜底时要**先扔掉**的元数据块（它们会霸占文本开头）
_META_BLOCKS = ("META", "CONTEXTE", "META_COMMUN", "META_SPEC", "META_ARTICLE")
# 法语字母范围（含变音），用于词边界断言
_FR_LETTERS = "a-zA-Z\u00c0-\u024f\u00c0-\u00ff"


def _kw_pattern(kw: str) -> "re.Pattern[str]":
    """把关键词编译成**词边界**正则。

    ⚠️ 为什么不能裸子串匹配：`KEYWORDS_FR` 里的 `"pile"`（电芯）
       用 `"pile" in text` 会命中 `compilation`、`empiler` 等无关词；
       `"VHU"` 同理。子串匹配会把无关法案拖进来（违反用户「不塞不相关结果」的约束）。

    支持法语常见变形（复数 / 形容词性数配合）：
        batterie → batteries；recyclé → recyclés / recyclée / recyclées；
        déchet → déchets。尾缀只加在**最后一个词**上，
        所以 `véhicule hors d'usage` 也能命中 `véhicules hors d'usage`。
    """
    suffix = r"(?:s|e|es|x|ee|ees|ée|ées|és)?"
    if " " in kw:
        head, _, last = kw.rpartition(" ")
        pat = rf"{re.escape(head)}\s+{re.escape(last)}{suffix}"
    else:
        pat = rf"{re.escape(kw)}{suffix}"
    return re.compile(
        rf"(?<![{_FR_LETTERS}]){pat}(?![{_FR_LETTERS}])", re.I)


def _date_from_name(name: str) -> "datetime | None":
    """从增量包文件名解析发布日期（否则 publish_date 永远是 None）。"""
    m = _NAME_DATE_RE.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None

# 本领域关键词（法语），**强词** —— 电池 / ELV / 黑粉的专有表述。
# 单独命中即可召回。
KEYWORDS_STRONG_FR: list[str] = [
    "batterie", "batteries", "accumulateur",
    "véhicule hors d'usage", "vehicule hors d'usage", "VHU",
    "dépollution", "masse noire", "broyage", "broyeur",
    "filière REP", "responsabilité élargie",
    "cobalt", "lithium",
]

# **通用词** —— 废物 / 循环类。
#
# ⚠️ 单独命中**不召回**。实测（2026-09-11，LEGI_20260910 增量）：
#    仅靠 `déchet`/`recyclage` 从 7,202 个 XML 里拖出 37 条，
#    其中 **36 条完全不含电池/ELV/黑粉任何核心名词**
#    （废纸分类、公共采购、疫苗接种中心……），相关率 2.7%。
#    这类词只能作为**辅助信号**（比如 "piles et accumulateurs usagés" 里
#    真正起作用的是 accumulateur）。
KEYWORDS_GENERIC_FR: list[str] = [
    "pile", "déchet", "recyclage", "recyclé", "métaux",
]

# 向后兼容：外部若直接引用 KEYWORDS_FR 仍可拿到全集
KEYWORDS_FR: list[str] = KEYWORDS_STRONG_FR + KEYWORDS_GENERIC_FR


class DilaFrConnector(BaseConnector):
    """法国 DILA 开放数据（LEGI / JORF 日增量）。"""

    source_id = "fr_dila"
    base_url = BASE
    timeout = 90.0

    # ⚠️ 该主机偶发返回空响应（curl code 0），必须重试
    RETRY_ON_EMPTY = 3

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
        # 强词单独命中即召回；通用词只在**强词缺席时**作为补充信号，
        # 且必须多个共现（单靠 `déchet` 会拖入废纸分类之类的无关文本）。
        kw_strong = [(_kw_pattern(k), k) for k in (keywords or KEYWORDS_STRONG_FR)]
        kw_generic = ([(_kw_pattern(k), k) for k in KEYWORDS_GENERIC_FR]
                      if keywords is None else [])
        files = await self.list_files(dataset, limit=max(latest, 1) * 2)
        if not files:
            raise ConnectorError(f"{self.source_id}: {dataset} 目录下没有找到增量包")

        out: list[RawEvidence] = []
        for name in files[:latest]:
            blob = await self._download_retry(name, dataset)
            if blob is None:
                continue
            hits = self._scan(blob, kw_strong, kw_generic, max_files_scanned)
            print(f"    {name}（{len(blob) / 1024:.0f} KB）→ 命中 {len(hits)} 个文本")
            for h in hits:
                # ⭐ URL 必须**唯一**：包 URL 会让同包多条法条在报告里去重掉。
                #    优先用 ELI 官链；拿不到时退回「包 URL#包内路径」保唯一。
                url = h.get("eli_url") or f"{BASE}/{dataset}/{name}#{h['file']}"
                out.append(RawEvidence(
                    evidence_id="",
                    channel="connector",
                    source_id=self.source_id,
                    source_url=url,
                    source_title=f"[DILA {dataset}] {h['title']}",
                    publish_date=_date_from_name(name),
                    raw_text=h["text"][:4000],
                    meta={
                        "country": "FR",
                        "region_hint": "EU-MemberState",
                        "dataset": dataset,
                        "archive": name,
                        "legi_file": h["file"],
                        "matched_terms": h["terms"],
                        "body_chars": h["body_chars"],
                        "archive_url": f"{BASE}/{dataset}/{name}",
                        "channel_note": "DILA 开放数据（Légifrance 原始源），日增量",
                    },
                ))
        return out

    async def _download_retry(self, name: str, dataset: str,
                              tries: int = 3) -> bytes | None:
        """带重试的下载。

        ⚠️ 该主机（echanges.dila.gouv.fr）**已知会瞬时失败**：
           实测出现过 curl 返回空（code 0）、以及 LEGI 大包下载报 ConnectorError。
           同一次运行里 JORF 成功、LEGI 失败 —— 完全是抖动，不是不可用。
           不重试就会把"这次没拿到"误记成"这个源不行"。
        """
        last: str = ""
        for attempt in range(tries):
            try:
                return await self._download(name, dataset)
            except Exception as exc:  # noqa: BLE001
                last = type(exc).__name__
                if attempt < tries - 1:
                    await asyncio.sleep(2.0 * (attempt + 1))
        print(f"    ⚠️ {name} 重试 {tries} 次仍失败（{last}）")
        return None

    async def _download(self, name: str, dataset: str = "LEGI") -> bytes:
        """下载增量包。

        ⚠️ 必须带上 dataset：曾经硬编码 `/LEGI/`，
           导致 `fetch(dataset="JORF")` 是**去 LEGI 目录下找 JORF 的文件**（必然 404）。
        """
        resp = await self._polite_get(f"{BASE}/{dataset}/{name}")
        return resp.content

    @staticmethod
    def _eli_url(content: str) -> str:
        """取法条的**官方可访问 URL**（Légifrance ELI 链接）。

        ⚠️ 为什么不能用增量包 URL 当 source_url：
           增量包里一个包含 7,202 个 XML（多个法条），若都用包 URL，
           下游 `make_report.load_records()` 按 URL 去重时会把
           **同一个包里的多条法条互相去重掉，只留下一 1 条**。

           实测（2026-09-11）：LEGI 召 37 条，报告中实际只剩 1 条。

           `<ID_ELI>` 是 Légifrance 的官方链接（人类可直接打开），
           天然唯一，既修去重又让报告里的链接可用。
        """
        m = re.search(r"<ID_ELI>\s*([^<\s]+)\s*</ID_ELI>", content, re.I)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_body(content: str) -> str:
        """从 DILA XML 里取出**法律正文**的纯文本。

        ⚠️ 为什么必须单独提取（而不是对整份文件剥标签）：
           DILA 的 XML 结构是 `<META>`（元数据）→ `<CONTEXTE>` → `<BLOC_TEXTUEL>`（正文）。
           `<META>` 里有 ID / ID_ELI / URL / NATURE / DATE_DEBUT / DATE_FIN 等字段，
           数量多、占位大。对整份文件剥标签后，**前几千字符全是这些机器字段**，
           真正的条文排在后面；而下游判定器只读 raw_text 的前 4000 字符，
           结果是「**正文确实存在，却被判成不相关**」。

           这是本项目同型缺陷的**第 4 例**，前三例：
             · 荷兰 KOOP `<work>` 壳（WTI 元数据，没有法条正文）
             · EUR-Lex `Q_CELEX` 缺 `expression_title`
             · EUR-Lex 元数据记录（只有 CELEX 号码，没有文本）

           通用教训：**「取到记录」≠「取到内容」**，
           必须在连接器层保证 raw_text 是**内容**而不是**指针**。
        """
        for tag in _BODY_TAGS:
            m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", content, re.S | re.I)
            if not m:
                continue
            raw = m.group(1)
            # <BLOC_TEXTUEL> 里常是**转义过的** HTML 片段（&lt;p&gt;…），先还原
            if "&lt;" in raw:
                raw = html.unescape(raw)
            text = _WS_RE.sub(" ", _TAG_RE.sub(" ", raw)).strip()
            if len(text) > 200:      # 太短的说明这个标签不是正文容器
                return text

        # ---- 兜底：没有正文容器时，先剥掉元数据块再剥标签 ----
        # 否则 <META> 里的 ID/URL/DATE_* 会霸占文本开头，判定器又只看得到机器字段。
        stripped = content
        for blk in _META_BLOCKS:
            stripped = re.sub(rf"<{blk}\b[^>]*>.*?</{blk}>", " ", stripped,
                              flags=re.S | re.I)
        return _WS_RE.sub(" ", _TAG_RE.sub(" ", stripped)).strip()

    def _scan(self, blob: bytes, kw_strong: list, kw_generic: list,
              max_files: int) -> list[dict]:
        """在 tar.gz 里逐文件扫关键词，命中即返回（含命中的词）。

        召回规则（实测调优，见 KEYWORDS_GENERIC_FR 注释）：
          1. 命中**强词** → 直接召回
          2. 只命中通用词 → 需 **≥2 个不同通用词共现** 才召回
        
        关键词匹配**只在「标题 + 正文」上做**，不在 `<META>` 元数据上做：
        元数据里的 URL（`article/JORF/ARTI/...`）和 ID 会制造无意义的假命中。
        """
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

            title = self._title(content, member.name)
            body = self._extract_body(content)
            haystack = f"{title}\n{body}"

            strong = [kw for rx, kw in kw_strong if rx.search(haystack)]
            generic = [kw for rx, kw in kw_generic if rx.search(haystack)] if not strong else []
            if not strong and len(generic) < 2:
                continue

            # 正文优先；正文提取失败才退回原文剥标签（并保证不是空指针）
            text = body or _WS_RE.sub(" ", _TAG_RE.sub(" ", content)).strip()
            hits.append({"file": member.name, "title": title,
                         "text": text, "terms": (strong + generic)[:6],
                         "body_chars": len(body),
                         "eli_url": self._eli_url(content)})
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
