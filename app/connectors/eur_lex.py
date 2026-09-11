"""欧盟立法连接器 —— SPARQL 元数据 + EUR-Lex 正文，双通道。

为什么不用 EUR-Lex 网页？
------------------------
实测（2026-09-10）：
    https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R1542
        → HTTP 202 + 挑战页（0 字节）；伪装 Chrome UA 仍是 202 → 被反爬
    https://eur-lex.europa.eu/eli/reg/2023/1542/oj
        → HTTP 202，同上
    https://publications.europa.eu/webapi/rdf/sparql
        → HTTP 200 application/sparql-results+json  ✅ 官方机器接口，无需鉴权

⭐ **上述结论已在 2026-09-11 被推翻一半 —— 关键是 Accept/UA 协商：**

    EUR-Lex HTML 直连（带浏览器 UA）
        https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32024R1157
        → HTTP 200，9.7 MB ✅ **正文可取**
    Cellar + `Accept: application/xhtml+xml`  → 200，9.7 MB ✅
    Cellar + `Accept: application/pdf`          → 200，4.7 MB ✅ 官方 PDF
    Cellar + `Accept: text/html`                → 404 ❌（**Accept 协商是真的**）

    教训：**"被反爬"的结论会过期**。源站会改策略，自己的请求头也会变。
    判死一个源之前，要重新测一遍 —— 否则会长期绕远路（此前一直靠 SPARQL 拿元数据，
    代价是**整层欧盟法规只有 CELEX 号、没有条文**）。

双通道分工
----------
    SPARQL（默认）—— 元数据：CELEX、ELI、生效日期、修订关系、更正版本
    EUR-Lex HTML —— 正文：法条原文，存快照到 sources/eurlex-fulltext/

SPARQL 本体字段（实测确认，勿臆造）
----------------------------------
    cdm:resource_legal_id_celex               CELEX 号
    cdm:resource_legal_eli                    ELI 标识
    cdm:resource_legal_type                   法规类型
    cdm:resource_legal_date_entry-into-force  生效日期
    cdm:resource_legal_date_end-of-validity   失效日期
    cdm:resource_legal_in-force               是否现行有效
    cdm:resource_legal_amends_resource_legal  修订了哪些法规
    cdm:resource_legal_repeals_resource_legal 废止了哪些法规
    cdm:resource_legal_codified_version       合并/编纂版本
    cdm:resource_legal_published_in_official-journal  官方公报出处
    cdm:resource_legal_responsibility_of_agent 责任机构
    cdm:work_date_document                    文件日期
    cdm:expression_title                      （多语言）标题
    cdm:expression_belongs_to_work            表达式→作品
"""

from __future__ import annotations

import asyncio
import html
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base import BaseConnector, ConnectorError, ProbeResult, RawEvidence, parse_date

# 正文快照目录：单个法规的 HTML 约 10 MB、纯文本约 40 万字符，
# **不能进 jsonl**（会把产出文件撑爆），必须落盘。
ROOT = Path(__file__).resolve().parent.parent.parent
FULLTEXT_DIR = ROOT / "sources" / "eurlex-fulltext"

SPARQL_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"
CDM = "http://publications.europa.eu/ontology/cdm#"

# ---------- 已实测通过的查询模板 ----------

Q_CELEX = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?celex ?eli ?type ?entryForce ?inForce ?date ?title
WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(STRSTARTS(STR(?celex), "{prefix}"))
  OPTIONAL {{ ?work cdm:resource_legal_eli ?eli }}
  OPTIONAL {{ ?work cdm:resource_legal_type ?type }}
  OPTIONAL {{ ?work cdm:resource_legal_date_entry-into-force ?entryForce }}
  OPTIONAL {{ ?work cdm:resource_legal_in-force ?inForce }}
  OPTIONAL {{ ?work cdm:work_date_document ?date }}
  # ⚠️ 标题是必需的，不是可选的装饰（2026-09-11 修复）：
  #   首版漏掉了这个 join，导致 CELEX 精确跟踪的法规**只有元数据、没有标题**，
  #   raw_text 里只有一个占位符 "EU legislation CELEX 32024R1157"。
  #   后果：黑粉第①条线「废物跨境转移」(EU) 2024/1157 被相关性判定默默丢弃——
  #   不是规则错，而是**根本没内容可判**。
  OPTIONAL {{
    ?expr cdm:expression_belongs_to_work ?work .
    ?expr cdm:expression_title ?title .
    FILTER(LANG(?title) = "en")
  }}
}}
LIMIT {limit}
"""

# 关键词发现：限定在立法（有 CELEX）范围内，避免全库扫描
#
# ⚠️ 实测教训（2026-09-10）：
#   朴素写法 `?work cdm:resource_legal_id_celex ?celex . ?work cdm:work_date_document ?date .`
#   再对 title 做 CONTAINS，会在整个 Cellar 库上做全表扫描 —— 单次查询超过 90 秒，
#   连续 7 个关键词直接拖垮采集。
#   修复：先用 **CELEX 年份前缀**（走索引）把候选集从百万级缩到万级，再做标题过滤。
#   CELEX 结构：sector(1) + year(4) + type(1) + number(4)，sector 3 = 立法。
Q_KEYWORD = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?celex ?title ?date
WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(REGEX(STR(?celex), "^(3)({celex_years})"))
  ?work cdm:work_date_document ?date .
  ?expr cdm:expression_belongs_to_work ?work .
  ?expr cdm:expression_title ?title .
  FILTER(CONTAINS(LCASE(STR(?title)), "{keyword}"))
}}
LIMIT {limit}
"""

# 按标题锚点找「以某部法为依据」的法案 —— **欧盟层的最大缺口在这里**
#
# 为什么必须单列这个查询
# ----------------------
# 电池法 (EU) 2023/1542 本身只是框架：真正落地义务的是它的
# **授权法案（delegated）与实施法案（implementing）**——
# 碳足迹计算方法、再生料含量核算、尽职调查、电池护照、回收效率……
# 这些一部都没被跟踪，等于"知道有法规，不知道具体要做什么"。
#
# 怎么找：这些法案的标题里**必然写明** supplementing/amending 的基础法号
#   e.g. "Commission Delegated Regulation (EU) 2025/606 supplementing
#         Regulation (EU) 2023/1542 ..."
# 所以按标题锚定字符串（"2023/1542"）检索最稳。
#
# ⚠️ 必须先按 CELEX 年份前缀收窄再做标题 CONTAINS ——
#    直接对全库标题做 CONTAINS 会全表扫描（见 Q_KEYWORD 的教训）。
# ⚠️ sector 3 = 正式立法，5 = 提案。两者都要（提案是监测信号）。
# ⚠️ 查询形状必须与已验证可用的 Q_KEYWORD **完全一致**。
#    实测教训（2026-09-11）：我加了三处"改进"——
#      · FILTER(LANG(?title)="en")  · OPTIONAL 日期/类型  · DISTINCT 多投影一个变量
#    结果查询直接**超时**（curl 60s / 150s 均无响应），而端点本身 1 秒就答。
#    回退成同形写法后立即返回。**在慢查询引擎上不要把工作版本的形状"顺手改好"。**
#    语言去重在 Python 侧做（同 _fetch_by_keyword 的做法）。
# ⚠️ sector：3 = 正式立法，5 = 提案。要用两次分别查，不要在正则里写 (3|5)。
Q_TITLE_ANCHOR = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?celex ?title ?date
WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(REGEX(STR(?celex), "^({sector})({years})"))
  ?work cdm:work_date_document ?date .
  ?expr cdm:expression_belongs_to_work ?work .
  ?expr cdm:expression_title ?title .
  FILTER(CONTAINS(STR(?title), "{anchor}"))
}}
LIMIT {limit}
"""

# ⭐ 批量按 CELEX 取记录 —— **实测比逐个查询快约 12 倍**
#
# 实测（2026-09-11，46 个跟踪法案的场景）：
#     逐个查询：单 CELEX 37s / 95s（均值 66s）→ 46 个需约 **40 分钟**
#     合并 10 个用 OR-STRSTARTS                 → 8.1s/个
#     合并 10 个用 **REGEX 交替**（本查询）      → **5.3s/个**
#
#   端点本身 1 秒就答（无过滤的全库计数查询）—— 慢的是 Virtuoso 的查询规划。
#   所以「减少查询次数」比「优化单次查询」有效得多。
#
# ⚠️ 前缀要用 `re.escape()` 转义：CELEX 里含 `(` `)`，
#    如 `32023R1542R(05)` —— 不转义会被当成正则分组。
# ⚠️⚠️ **形状必须是计时实测过的那个精简版**。
#
# 踩过的坑（2026-09-11）：我先把完整元数据形状（Q_CELEX 那套，6 个 OPTIONAL
# + DISTINCT 8 变量）直接拿去批量，结果 6 批里 **5 批超时失败**（httpx 90s /
# curl 60s 都不够）；而计时测试用的是下面这个精简形状，10 个前缀只要 52s。
#
# **计时测试用的形状，就是上线能用的形状。换成"更全的"就得重新计时。**
#
# 拿掉的：eli / type / inForce / entryForce（漂亮但非必需）。
# 保留的：work / celex / date / title —— 建记录够用，正文另有 _with_fulltext 补。
Q_CELEX_BATCH = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT DISTINCT ?work ?celex ?date ?title
WHERE {{
  ?work cdm:resource_legal_id_celex ?celex .
  FILTER(REGEX(STR(?celex), "^({pattern})"))
  ?work cdm:work_date_document ?date .
  ?expr cdm:expression_belongs_to_work ?work .
  ?expr cdm:expression_title ?title .
}}
LIMIT {limit}
"""

# 单部法规的关系图（修订 / 废止 / 合并版本）
Q_RELATIONS = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?predicate ?object
WHERE {{
  <{work}> ?predicate ?object .
  FILTER(?predicate IN (
    cdm:resource_legal_amends_resource_legal,
    cdm:resource_legal_repeals_resource_legal,
    cdm:resource_legal_codified_version,
    cdm:resource_legal_based_on_resource_legal,
    cdm:resource_legal_published_in_official-journal,
    cdm:resource_legal_responsibility_of_agent,
    cdm:resource_legal_is_about_concept_eurovoc
  ))
}}
LIMIT 200
"""

# 电池回收主题相关的 CELEX 前缀（法规/指令/决定三大类）
DEFAULT_CELEX_PREFIXES = ["32023R1542", "32006L0066", "32025R", "32024R"]

# 领域关键词（英文），用于标题发现
DEFAULT_KEYWORDS = [
    "battery",
    "batteries",
    "recycled content",
    "due diligence batter",
]


class EurLexConnector(BaseConnector):
    """欧盟立法连接器（SPARQL）。"""

    source_id = "eu_eurlex"
    base_url = SPARQL_ENDPOINT
    # ⚠️ 必须给足：单次 SPARQL 实测 37s~95s **波动极大**（Virtuoso 冷/热缓存
    #    与查询规划差异）。曾用 90s，结果批量查询 6 批里 5 批超时。
    #    curl 回退也用这个值（base.py 已改为读 self.timeout）。
    timeout = 240.0

    # ---------- 底层 ----------
    async def _sparql(self, query: str) -> list[dict[str, Any]]:
        resp = await self._polite_get(
            self.base_url,
            params={"query": query, "format": "application/sparql-results+json"},
        )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ConnectorError(f"{self.source_id}: SPARQL 返回非 JSON") from exc

        if "results" not in payload:
            # Virtuoso 出错时返回 200 + 错误文本
            err = str(payload)[:300]
            raise ConnectorError(f"{self.source_id}: SPARQL 查询错误 {err}")
        return payload["results"].get("bindings", [])

    @staticmethod
    def _val(binding: dict[str, Any], key: str) -> str | None:
        node = binding.get(key)
        return node.get("value") if node else None

    @staticmethod
    def _lang(binding: dict[str, Any], key: str) -> str | None:
        node = binding.get(key)
        return node.get("xml:lang") if node else None

    # ---------- 公开能力 ----------
    async def fetch(self, query: str | None = None, **kwargs: Any) -> list[RawEvidence]:
        """
        query 支持三种写法：
          "celex:32023R1542"        → 精确跟踪某部法规及其更正版本
          "keyword:battery"         → 标题关键词发现
          None                      → 用默认前缀 + 默认关键词做一轮增量发现
        """
        limit = int(kwargs.get("limit", 50))
        since = kwargs.get("since", "2024-01-01")
        out: list[RawEvidence] = []

        if query and query.startswith("celex:"):
            out += await self._fetch_by_celex(query.split(":", 1)[1], limit)
        elif query and query.startswith("keyword:"):
            out += await self._fetch_by_keyword(query.split(":", 1)[1], since, limit)
        else:
            for prefix in DEFAULT_CELEX_PREFIXES:
                out += await self._fetch_by_celex(prefix, limit)
            for kw in DEFAULT_KEYWORDS:
                out += await self._fetch_by_keyword(kw, since, limit)

        return self._dedupe(out)

    async def _fetch_by_celex(self, prefix: str, limit: int) -> list[RawEvidence]:
        bindings = await self._sparql(Q_CELEX.format(prefix=prefix, limit=limit))
        out: list[RawEvidence] = []
        seen: set[str] = set()
        for b in bindings:
            celex = self._val(b, "celex")
            if not celex or celex in seen:
                continue
            seen.add(celex)
            work = self._val(b, "work")
            title = self._val(b, "title") or ""
            out.append(RawEvidence(
                evidence_id=f"eu_{celex}",
                channel="connector",
                source_id="eu_eurlex_battery_reg",
                # ⭐ 用可读的 EUR-Lex 链接，不用 Cellar 的不透明 UUID：
                #    研究者要能一眼看出这是哪部法规、点开就能读。
                source_url=self._eurlex_url(celex),
                source_title=(f"{title} [CELEX {celex}]" if title
                              else f"EU legislation CELEX {celex}"),
                publish_date=parse_date(
                    self._val(b, "entryForce") or self._val(b, "date")
                ),
                raw_text=self._with_fulltext(celex, self._render(celex, b)),
                meta={
                    "celex": celex,
                    "title_en": title,
                    "eli": self._val(b, "eli"),
                    "type": self._val(b, "type"),
                    "in_force": self._val(b, "inForce"),
                    "entry_into_force": self._val(b, "entryForce"),
                    "corrigendum": bool(re.search(r"R\(\d+\)$", celex)),
                    "work": work,
                },
            ))
        return out

    async def _fetch_by_keyword(self, keyword: str, since: str, limit: int) -> list[RawEvidence]:
        # 从 since 年份推出 CELEX 年份正则，如 "2024-01-01" → "202[4-9]"
        start_year = int((since or "2024")[:4])
        celex_years = f"202[{start_year % 10}-9]"
        bindings = await self._sparql(
            Q_KEYWORD.format(keyword=keyword.lower(), celex_years=celex_years, limit=limit)
        )
        out: list[RawEvidence] = []
        seen: set[str] = set()
        skipped_langs: set[str] = set()
        for b in bindings:
            celex = self._val(b, "celex")
            lang = self._lang(b, "title")
            if not celex:
                continue
            # ⚠️ 实测：同一 CELEX 会返回 da/de/en/fr/it/... 多语言标题。
            #    这是**同一条法规**的不同语言版本，不是多条法规。
            #    只保留英文版本，否则同一条法规会在库里重复 5~24 次，
            #    既污染去重统计，又让"独立来源计数"虚高（影响交叉验证）。
            if lang != "en":
                skipped_langs.add(lang or "und")
                continue
            if celex in seen:
                continue
            seen.add(celex)
            title = self._val(b, "title") or ""
            work = self._val(b, "work")
            out.append(RawEvidence(
                evidence_id=f"eu_{celex}",
                channel="connector",
                source_id="eu_eurlex_keyword",
                source_url=self._eurlex_url(celex),
                source_title=title,
                publish_date=parse_date(self._val(b, "date")),
                raw_text=self._with_fulltext(celex, title),
                meta={
                    "celex": celex,
                    "title_en": title,
                    "lang": lang,
                    "discovered_by": keyword,
                    "work": work,
                    "other_langs": sorted(skipped_langs),
                },
            ))
        return out

    # ---------- 正文（EUR-Lex HTML）----------
    @staticmethod
    def _with_fulltext(celex: str, base_text: str, chars: int = 12000) -> str:
        """若磁盘已有正文快照，把它并进 raw_text。

        ⚠️ 为什么必须并：SPARQL 只给元数据，raw_text 里只有
           "EU legislation CELEX 32000L0053" 这种占位符 →
           **相关性判定根本没有内容可判** → 整部法规被静默丢弃。

           实测（2026-09-11）：报废车指令 2000/53/EC（ELV 主干法）
           就因为这个原因被判为不相关，尽管它的全文早已落盘在
           `sources/eurlex-fulltext/32000L0053.txt`。

           这与荷兰 BWB 取到 `<work>` 空壳、以及 Q_CELEX 早期漏掉
           `expression_title` 是**同一类问题**：
             记录存在，但内容为空。
        """
        path = FULLTEXT_DIR / f"{celex}.txt"
        if not path.exists():
            return base_text
        try:
            body = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            return base_text
        return f"{base_text}\n\n[正文快照 {path.name}，{len(body)} 字符]\n{body[:chars]}"

    # ---------- 正文（EUR-Lex HTML）----------
    # 为什么必须有这条通道：SPARQL 只给元数据。整个欧盟层曾长期"只有 CELEX 号、
    # 没有条文"，导致报告里只能列出法规清单，无法引用"第 X 条规定了什么"。
    #
    # ⚠️ 抓取要点（实测 2026-09-11）：
    #   · URL 用 .../legal-content/EN/TXT/HTML/?uri=CELEX:<celex>
    #   · 单个文件约 10 MB HTML / 约 40 万字符纯文本 —— **不要放进 jsonl**，
    #     必须落盘到 sources/eurlex-fulltext/，jsonl 里只存路径与摘要
    async def fetch_fulltext(self, celex: str,
                             save: bool = True) -> tuple[str, Any]:
        """抓取法规/指令正文，返回 (纯文本, 快照路径)。

        正文提取策略（两层，先精确后兜底）：
          ① 定位 `id="documentView"` 容器（EUR-Lex 的正文容器）
          ② 兜底：从"The European Parliament / The Council"起，
             到"shall be binding"止 —— 掐掉页头导航与页脚
        """
        url = (f"https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/"
               f"?uri=CELEX:{celex}")
        resp = await self._polite_get(url)
        text = self._extract_body(resp.text)

        dest = None
        if save and text:
            FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
            dest = FULLTEXT_DIR / f"{celex}.txt"
            dest.write_text(
                f"# CELEX {celex}\n# {self._eurlex_url(celex)}\n"
                f"# 抓取 {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
                f"（正文 {len(text)} 字符）\n\n{text}",
                encoding="utf-8")
        return text, dest

    @staticmethod
    def _extract_body(raw_html: str) -> str:
        """从 EUR-Lex HTML 抽出法条正文（去掉页面框架）。"""
        if not raw_html:
            return ""
        s = raw_html

        # ① 优先用正文容器
        m = re.search(r'(?is)<div[^>]+id="documentView"[^>]*>(.*?)</div>\s*</div>', s)
        body = m.group(1) if m else ""

        # ② 兜底：用起止标记夹出正文
        if len(body) < 5000:
            starts = [s.find(k) for k in (
                "THE EUROPEAN PARLIAMENT", "THE COUNCIL OF THE EUROPEAN",
                "THE EUROPEAN COMMISSION", "THE EUROPEAN CENTRAL BANK")]
            starts = [i for i in starts if i > 0]
            if starts:
                beg = min(starts)
                ends = [s.find(k, beg) for k in (
                    "This Regulation shall be binding",
                    "This Directive shall be binding",
                    "This Decision shall be binding",
                    "Done at ")]
                ends = [i for i in ends if i > beg]
                body = s[beg:min(ends) + 200] if ends else s[beg:]

        if not body:
            body = s

        # 去脚本/样式/注释
        body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", body)
        body = re.sub(r"(?s)<!--.*?-->", " ", body)
        # 块级标签转换行，行内标签去空格
        body = re.sub(r"(?i)<(br|/p|/div|/tr|/h[1-6]|/li|/td)[^>]*>", "\n", body)
        body = re.sub(r"<[^>]+>", " ", body)
        body = html.unescape(body).replace("\u00a0", " ")
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n\s*\n+", "\n", body)
        return body.strip()

    async def fetch_relations(self, work_uri: str) -> dict[str, list[str]]:
        """拉取某部法规的修订/废止/合并版本关系图。"""
        bindings = await self._sparql(Q_RELATIONS.format(work=work_uri))
        rel: dict[str, list[str]] = {}
        for b in bindings:
            p = self._val(b, "predicate") or ""
            o = self._val(b, "object") or ""
            rel.setdefault(p.replace(CDM, ""), []).append(o)
        return rel

    async def find_acts_by_title(self, anchor: str,
                                 years: str = "20(2[3-9])",
                                 limit: int = 120,
                                 sectors: tuple[str, ...] = ("3", "5")) -> list[dict[str, Any]]:
        """按标题锚点找「以某部法为依据」的法案（授权/实施/修订/提案）。

        参数
        ----
        anchor : 出现在标题里的基础法号，如 "2023/1542"（电池法）、
                 "2000/53/EC"（报废车指令）、"2024/1157"（废物运输）
        years  : CELEX 年份正则片段（**必须先收窄再做标题 CONTAINS**，
                 否则全表扫描；见 Q_KEYWORD 的实测教训）
        sectors: 3=正式立法 5=提案。**分两次查**，不要写成 (3|5) ——
                 实测那样会超时（见 Q_TITLE_ANCHOR 注释）。
        """
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for sector in sectors:
            try:
                rows = await self._sparql(Q_TITLE_ANCHOR.format(
                    anchor=anchor, years=years, limit=limit, sector=sector))
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ 锚点 {anchor} sector={sector} 失败：{type(exc).__name__}")
                continue
            for b in rows:
                celex = self._val(b, "celex")
                if not celex or celex in seen:
                    continue
                # 语言去重（同 _fetch_by_keyword：只要英文标题）
                if self._lang(b, "title") not in ("en", None):
                    continue
                seen.add(celex)
                out.append({
                    "celex": celex,
                    "title": self._val(b, "title") or "",
                    "date": self._val(b, "date"),
                    "sector": "提案" if sector == "5" else "立法",
                    "work": self._val(b, "work"),
                })
        return out

    async def fetch_celex_batch(self, prefixes: list[str],
                                limit: int = 1500,
                                chunk: int = 4,
                                tries: int = 3) -> list[RawEvidence]:
        """批量按 CELEX 前缀取记录（一次查询合并多个前缀）。

        语义与逐个 `fetch("celex:xxx")` 一致：前缀匹配会顺带覆盖
        该法的更正版本（`32023R1542` → 也命中 `32023R1542R(05)`）。

        ⚠️ 必须批量：见 Q_CELEX_BATCH 注释 —— 46 次单查约 40 分钟。
        ⚠️⚠️ **必须重试**：这个端点在本会话里反复抖动 —— 同一批前缀，
           独立测试 105 秒成功返回 37 条，放到采集流程里却整批
           ConnectorError（8 批里挂 6 批）。加大超时到 240s 也治不好。
           这与法国 DILA、ECHA 的抖动是同一类问题：
           **瞬时失败不能当成"这个源不行"**，要重试后再下结论。
        ⚠️ chunk 默认 4（而非 6）：前缀越多单次查询越重，抖动概率越高。
        """
        out: list[RawEvidence] = []
        # celex → 已选中的标题；同一 CELEX 会有多语言标题，优先英文
        picked: dict[str, dict[str, Any]] = {}
        batches = [prefixes[i:i + chunk] for i in range(0, len(prefixes), chunk)]
        for idx, group in enumerate(batches, 1):
            _t0 = time.monotonic()
            pattern = "|".join(re.escape(p) for p in group)
            # ⚠️⚠️ **SPARQL 字符串层转义**（2026-09-11 修复，5 个批次反复失败的唯一根因）
            #
            #   re.escape("...R(01)") → "...R\(01\)"。这里的 `\(` 是给 **Python 正则**
            #   用的转义，直接写进 SPARQL 短字符串就是**非法转义序列**：
            #     SP030: Bad escape sequence in a short double-quoted string
            #            at '"^(52025PC0501R\'
            #   → Virtuoso 拒收 → **HTTP 400**（不是超时，不是抖动）。
            #
            #   ⚠️ 表现极具迷惑性：**只有含 `(` 的 CELEX（即更正版 R(01)/R(02)）
            #      才会触发**。于是“12 批里偏偏那 5 批失败”，看起来像随机抖动，
            #      实际上完全确定（同一批前缀连续两轮采集失败得一模一样）。
            #
            #   SPARQL 里 `\\` 才表示一个反斜杠 → 正则引擎收到的仍是 `\(`，语义不变。
            safe = pattern.replace("\\", "\\\\")
            rows: list[dict[str, Any]] = []
            last_err = ""
            for attempt in range(1, tries + 1):
                try:
                    rows = await self._sparql(
                        Q_CELEX_BATCH.format(pattern=safe, limit=limit))
                    last_err = ""
                    break
                except Exception as exc:  # noqa: BLE001
                    # ⚠️ 必须带消息：只留 `type(exc).__name__` 的话，日志里
                    #    永远只有「ConnectorError」四个字，分不清是超时、
                    #    HTTP 状态还是 Virtuoso 规划失败 —— 那等于把线索丢掉。
                    last_err = f"{type(exc).__name__}: {str(exc)[:300]}"
                    if attempt < tries:
                        await asyncio.sleep(3.0 * attempt)
            if last_err:
                print(f"    ⚠️ 批量 {idx}/{len(batches)}"
                      f"（{group[0]}…）重试 {tries} 次仍失败：{last_err}")
                continue

            got_before = len(picked)
            for b in rows:
                celex = self._val(b, "celex")
                if not celex:
                    continue
                lang = self._lang(b, "title")
                cur = picked.get(celex)
                # 优先保留英文标题；非英文仅在还没选中时启用
                if cur is not None and (cur["lang"] == "en" or lang != "en"):
                    continue
                picked[celex] = {
                    "lang": lang or "",
                    "work": self._val(b, "work"),
                    "title": self._val(b, "title") or "",
                    "date": self._val(b, "date"),
                }
            print(f"    批量 {idx}/{len(batches)} → {len(rows)} 行"
                  f"（新增 {len(picked) - got_before} 个 CELEX）"
                  f" {time.monotonic() - _t0:5.1f}s")

        for celex, info in picked.items():
            title = info["title"]
            out.append(RawEvidence(
                evidence_id=f"eu_{celex}",
                channel="connector",
                source_id="eu_eurlex_battery_reg",
                source_url=self._eurlex_url(celex),
                source_title=(f"{title} [CELEX {celex}]" if title
                              else f"EU legislation CELEX {celex}"),
                publish_date=parse_date(info["date"]),
                raw_text=self._with_fulltext(
                    celex,
                    (f"EU legislation CELEX {celex}\n{title}\n"
                     f"Date: {info['date'] or ''}")),
                meta={
                    "celex": celex,
                    "title_en": title,
                    "title_lang": info["lang"],
                    "corrigendum": bool(re.search(r"R\(\d+\)$", celex)),
                    "work": info["work"],
                    "batched": True,
                },
            ))
        return out

    # ---------- 探测 ----------
    async def probe(self) -> ProbeResult:
        import time as _t
        t0 = _t.monotonic()
        try:
            rows = await self._sparql(
                Q_CELEX.format(prefix="32023R1542", limit=20)
            )
            return ProbeResult(
                source_id=self.source_id,
                reachable=True,
                status_code=200,
                latency_ms=int((_t.monotonic() - t0) * 1000),
                records_found=len(rows),
                sample=[self._val(r, "celex") or "?" for r in rows[:5]],
            )
        except Exception as exc:  # noqa: BLE001 —— 探测需吞掉所有异常并如实上报
            return ProbeResult(
                source_id=self.source_id,
                reachable=False,
                status_code=None,
                latency_ms=int((_t.monotonic() - t0) * 1000),
                records_found=0,
                blocked="拦截" in str(exc),
                error=str(exc),
            )

    # ---------- 工具 ----------
    @staticmethod
    def _eurlex_url(celex: str) -> str:
        """CELEX → 人类可读的 EUR-Lex 链接。

        为什么不直接用 Cellar 的 work URI：
            那些 URI 形如 publications.europa.eu/resource/cellar/d0065c31-2ce3-11ee-…
            是**不透明的 UUID**，研究者无法从中判断这是哪部法规。
            EUR-Lex 的 CELEX 链接点开直接就是法规正文，且带语言与格式选项。
        """
        return f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"

    @staticmethod
    def _render(celex: str, b: dict[str, Any]) -> str:
        """把结构化字段渲染成可读文本，便于后续抽取与人工核阅。"""
        get = lambda k: (b.get(k) or {}).get("value")  # noqa: E731
        lines: list[str] = []
        title = get("title")
        if title:
            lines.append(f"标题: {title}")
        lines.append(f"CELEX: {celex}")
        for label, key in (
            ("类型", "type"), ("生效", "entryForce"), ("现行有效", "inForce"),
            ("ELI", "eli"), ("文件日期", "date"),
        ):
            if get(key):
                lines.append(f"{label}: {get(key)}")
        lines.append("原文链接: " + EurLexConnector._eurlex_url(celex))
        return "\n".join(lines)

    @staticmethod
    def _dedupe(items: list[RawEvidence]) -> list[RawEvidence]:
        seen: set[str] = set()
        out: list[RawEvidence] = []
        for it in items:
            if it.evidence_id in seen:
                continue
            seen.add(it.evidence_id)
            out.append(it)
        return out
