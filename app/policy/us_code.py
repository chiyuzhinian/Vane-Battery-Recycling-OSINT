# -*- coding: utf-8 -*-
"""US Code / Public Law 身份与关系（Phase 4B-1 Step 4）—— 纯逻辑，无网络。

官方通道（govinfo，实测 2026-09-12 全 200）：
    USC : content/pkg/USCODE-{year}-title{t}/html/USCODE-{year}-title{t}-chap{c}.htm
    PLAW: content/pkg/PLAW-{c}publ{n}/html/PLAW-{c}publ{n}.htm
    |congress 枚举: wssearch/rb/plaw（119/118/117… + docCount）

实测 HTML 格式（2026-09-12）：
    USC 条文清单是两栏分析表：
      <div class="two-column-analysis-style-content-left">6921.</div>
    正文引用形如 [42 U.S.C. 6921]；
    不存在章节会返回伪 404（HTTP 200 + <title>Page Not Found</title>）→ 必须显式识别。

关系（全部**官方文本证据**，不由标题猜测）：
    PL  → AMENDS / CODIFIED_AS → USC   （"to amend title 42, United States Code" 等）
    CFR → AUTHORIZED_BY        → USC   （eCFR <AUTH> 权威注记）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")


def strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "",
                  flags=re.I | re.S)
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def usc_key(title: int | str, section: int | str = "") -> str:
    return f"USC:{title}:{section}" if section != "" else f"USC:{title}"


def pl_key(congress: int | str, number: int | str) -> str:
    return f"PL:{congress}-{number}"


# ------------------------------------------------------------ USC

@dataclass
class UscChapter:
    title: int
    chapter: str
    year: str = ""
    heading: str = ""
    sections: list[str] = field(default_factory=list)
    text_head: str = ""

    @property
    def key(self) -> str:
        return usc_key(self.title, f"chap{self.chapter}")

    @property
    def canonical_title(self) -> str:
        head = self.heading.split(" - ", 1)[-1].strip()
        return (f"U.S.C. Title {self.title} Chapter {self.chapter}"
                + (f" — {head}" if head else ""))


_HEADING_RE = re.compile(r"U\.S\.C\.\s*Title\s*(\d+)\s*-\s*([^<]+)", re.I)
_SECTION_RE = re.compile(r"§\s*(\d+[A-Za-z]?(?:-\d+)?)")
#: govinfo USC HTML 的条文清单采用两栏分析表：
#: <div class="two-column-analysis-style-content-left">6921.</div>
_ANALYSIS_LEFT_RE = re.compile(
    r'two-column-analysis-style-content-left">\s*(\d+[A-Za-z]?)\.\s*<')
#: 正文引用形式：[42 U.S.C. 6921]
_BRACKET_CITE_RE = re.compile(r"\[(\d{1,2})\s+U\.S\.C\.\s+(\d+[A-Za-z]?)\]")


def is_not_found_page(html_text: str) -> bool:
    """govinfo 的伪 404：HTTP 200 但内容为 'Page Not Found' 页面。"""
    head = (html_text or "")[:3000]
    return ("<title>Page Not Found" in head
            or "Govinfo Bulkdata Service Error" in head)


def parse_us_code_chapter(html_text: str, *, title: int, chapter: str,
                          year: str = "") -> UscChapter:
    raw = html_text or ""
    if is_not_found_page(raw):
        raise ValueError("USC 页面不存在（govinfo 伪 404：Page Not Found）")
    out = UscChapter(title=title, chapter=str(chapter), year=year)
    m = _HEADING_RE.search(raw)
    if m:
        out.heading = f"{m.group(1)} - {m.group(2)}".strip()
    flat = strip_html(raw)
    seen: list[str] = []
    # ① 分析表（章节清单）——govinfo 新格式主通道
    for s in _ANALYSIS_LEFT_RE.findall(raw):
        if s not in seen:
            seen.append(s)
    # ② 方形引用 [42 U.S.C. 6921]
    if not seen:
        for t, s in _BRACKET_CITE_RE.findall(raw):
            if int(t) == title and s not in seen:
                seen.append(s)
    # ③ 老的 § 号形式
    if not seen:
        for s in _SECTION_RE.findall(flat):
            if s not in seen:
                seen.append(s)
    out.sections = seen
    out.text_head = flat[:1200]
    if not seen and not out.heading:
        raise ValueError("USC 页面解析失败（无标题且无条文）")
    return out


# ------------------------------------------------------------ Public Law

@dataclass
class PublicLaw:
    congress: int
    number: int
    heading: str = ""
    stat_citation: str = ""
    enactment_note: str = ""
    usc_mentions: list[str] = field(default_factory=list)
    cfr_mentions: list[str] = field(default_factory=list)
    amended_titles: list[str] = field(default_factory=list)
    note_mentions: list[str] = field(default_factory=list)
    text_head: str = ""

    @property
    def key(self) -> str:
        return pl_key(self.congress, self.number)


_PL_HEADER_RE = re.compile(
    r"\[(\d+)(?:st|nd|rd|th)\s+Congress\s+Public\s+Law\s+(\d+)\]", re.I)
_STAT_RE = re.compile(r"\[\[\s*Page\s+([\d\s]+?)\s*STAT\.\s*([\d]+)\s*\]\]")
#: "to amend title 42, United States Code" / "amending title 49, U.S.C."
_AMEND_TITLE_RE = re.compile(
    r"amend\w*\s+(?:title\s+)?(\d{1,2})\s*,?\s*(?:United States Code|U\.?\s?S\.?\s?C\.?)",
    re.I)
_USC_MENTION_RE = re.compile(
    r"\b(\d{1,2})\s+U\.?\s?S\.?\s?C\.?\s+(?:§+\s*)?(\d+[A-Za-z]?(?:\([a-z0-9]+\))*)",
    re.I)
_CFR_MENTION_RE = re.compile(r"\b(\d{1,3})\s+CFR\s+(?:part\s+|§\s*)?(\d+[A-Za-z.]*)", re.I)
#: govinfo 官方边缘注记（实测 IRA）：&lt;&lt;NOTE: 26 USC 55.&gt;&gt; → "<<NOTE: 26 USC 55.>>"
#: 这是 GPO 标注的“该节涉及/修改 U.S.C. 某条”的官方证据
_NOTE_CITE_RE = re.compile(r"NOTE:\s*(\d{1,2})\s+USC\s+([0-9A-Za-z]+)", re.I)


def parse_public_law(html_text: str) -> PublicLaw:
    raw = html_text or ""
    m = _PL_HEADER_RE.search(raw[:4000])
    if not m:
        raise ValueError("PLAW 页面缺少 '[Xth Congress Public Law N]' 头")
    pl = PublicLaw(congress=int(m.group(1)), number=int(m.group(2)))

    flat = strip_html(raw)
    sm = _STAT_RE.search(raw[:12_000])
    if sm:
        pl.stat_citation = f"{sm.group(1).strip()} STAT. {sm.group(2)}"
    lines = [l.strip() for l in flat.split("  ") if l.strip()]
    for line in lines[:6]:
        if line.lower().startswith(("an act", "joint resolution", "public law")):
            pl.heading = line
            break
    if not pl.heading:
        pl.heading = lines[0][:300] if lines else ""

    for c, s in _USC_MENTION_RE.findall(flat):
        cite = f"{int(c)} U.S.C. {s}"
        if cite not in pl.usc_mentions:
            pl.usc_mentions.append(cite)
    for t, p in _CFR_MENTION_RE.findall(flat):
        cite = f"{int(t)} CFR {p}"
        if cite not in pl.cfr_mentions:
            pl.cfr_mentions.append(cite)
    for t in _AMEND_TITLE_RE.findall(flat):
        key = usc_key(int(t))
        if key not in pl.amended_titles:
            pl.amended_titles.append(key)
    for t, s in _NOTE_CITE_RE.findall(flat):
        cite = f"{int(t)} U.S.C. {s}"
        if cite not in pl.note_mentions:
            pl.note_mentions.append(cite)
        if cite not in pl.usc_mentions:
            pl.usc_mentions.append(cite)
    pl.text_head = flat[:1500]
    return pl


def pl_relations(pl: PublicLaw) -> list[dict]:
    """PL → USC 关系（官方文本证据）。"""
    out: list[dict] = []
    for key in pl.amended_titles:
        out.append({"from_key": pl.key, "to_key": key, "relation": "AMENDS",
                    "relation_evidence": "PL 文本：'to amend title N, United States Code'"})
    for cite in pl.note_mentions:
        parts = cite.split(" ")
        out.append({"from_key": pl.key,
                    "to_key": usc_key(int(parts[0]), parts[-1]),
                    "relation": "AMENDS",
                    "relation_evidence": "govinfo 官方边缘注记（NOTE: NN USC sss）"})
    for cite in pl.usc_mentions:
        parts = cite.split(" ")
        t = parts[0]
        out.append({"from_key": pl.key,
                    "to_key": usc_key(int(t), parts[-1]),
                    "relation": "CODIFIED_AS",
                    "relation_evidence": "PL 文本 U.S.C. 引用"})
    # 去重（NOTE 注记可能同时产生 AMENDS 与 CODIFIED_AS）
    seen: set[tuple[str, str, str]] = set()
    uniq: list[dict] = []
    for r in out:
        k = (r["to_key"], r["relation"], r["relation_evidence"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq


# ------------------------------------------------------------ 相关条款摘录

#: 相关条款摘录关键词（防止大法（如 IIJA 3.8MB）的电池条款被截断丢失）
_EXCERPT_KEYS = ("battery", "batteries", "black mass", "critical mineral",
                 "lithium", "recycl", "recycling", "electric vehicle",
                 "hazardous waste", "solid waste",
                 "clean vehicle", "tax credit")


def relevance_excerpts(flat_text: str, *, window: int = 400,
                       limit: int = 8) -> str:
    """在全文（已去标签）中定位相关条款片段 → 供 acceptance 判据使用。

    ⚠️ 调用方必须把结果放在记录 text 的**前部**：acceptance 只扫描前 1600 字符。
    """
    low = (flat_text or "").lower()
    spans: list[tuple[int, int]] = []
    for kw in _EXCERPT_KEYS:
        start = 0
        while len(spans) < limit * 2:
            i = low.find(kw, start)
            if i < 0:
                break
            spans.append((max(0, i - window // 2), i + window // 2))
            start = i + len(kw)
    spans.sort()
    merged: list[list[int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    chunks = [flat_text[s:e].strip() for s, e in merged[:limit]]
    return "\n…\n".join(c for c in chunks if c)


# ------------------------------------------------------------ CFR → USC（权威注记桥）

def build_cfr_usc_links(cfr_records: list[dict]) -> list[dict]:
    """eCFR 记录（meta.usc_citations）→ AUTHORIZED_BY → USC 边。"""
    out: list[dict] = []
    for rec in cfr_records or []:
        meta = rec.get("meta") or {}
        cfr_key = meta.get("cfr_key") or ""
        if not cfr_key:
            continue
        for cite in meta.get("usc_citations") or []:
            parts = cite.split(" ")
            if len(parts) < 3:
                continue
            out.append({
                "from_key": cfr_key,
                "to_key": usc_key(int(parts[0]), parts[-1]),
                "relation": "AUTHORIZED_BY",
                "from_doc": rec.get("evidence_id", ""),
                "relation_evidence": "eCFR <AUTH> 权威注记",
            })
    return out
