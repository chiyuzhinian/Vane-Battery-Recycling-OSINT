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

import html
import re
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
    timeout = 90.0        # SPARQL 查询较慢，实测单次 10-60s

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
