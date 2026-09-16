# -*- coding: utf-8 -*-
"""run_jurisdiction_round.py —— 管辖地级 MODE A/B 轮执行器（Phase 4B-2A Step 8）。

与 run_discovery_round.py 同样的协议（plan 绑定 / validity / 双指标），
但作用于**管辖地级 plan**（scope == jurisdiction_id，如 SE）。

路线语义（自管辖地端点派生的 4 类独立路线）：
    A 官方枚举     ：plan.fr_agencies（文号/section 直链种子）→ 抓全文
    B 母语全文检索 ：plan.fr_terms → 官方检索页 → 解析新文号 → 抓全文
    C 引用扩展     ：plan.eu_keywords（显式引用种子）+ 已采语料正文引用抽取 → 回采
    D 缺口枚举     ：plan.cross_terms（显式缺口种子）→ 回采

支持管辖地：SE / FI / US-CA / US-WA / CZ / IT / HU / SK（其余如实拒绝——通道未适配）。
（MODE B 批次 1：CZ/IT/HU/SK 适配器，2026-09-15）
每个管辖地的 search/fetch 实现复用 leg_utils 解析基元；证据字段口径与
正式连接器一致（evidence_id / doc_key / jurisdiction / source_role）。

用法：
    py scripts/run_jurisdiction_round.py --plan SE_PLAN_V1 --mode discovery --round 1
    py scripts/run_jurisdiction_round.py --show

产物：
    outputs/discovery_rounds/round_{scope}_{n}_{ts}.json
    outputs/round_{scope}_{n}_{ts}.jsonl（新入选文档）
    outputs/audit/discovery_rounds.json（索引，与联邦轮共用）
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import html as html_mod
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.connectors.leg_utils import (  # noqa: E402
    detect_challenge, extract_next_flight, extract_text_nodes, strip_html,
    trim_nav,
)
from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.backfill import load_records  # noqa: E402
from app.policy.rounds import (  # noqa: E402
    ACCEPTED_CLASSES, RouteResult, build_round_record, convergence_status,
    derive_validity, now_iso,
)
from app.policy.search_plan import load_plan, validate_plan  # noqa: E402

ROUNDS_DIR = ROOT / "outputs" / "discovery_rounds"
INDEX = ROOT / "outputs" / "audit" / "discovery_rounds.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
SUPPORTED = ("SE", "FI", "US-CA", "US-WA", "CZ", "IT", "HU", "SK",
             "AT")


class DocNotFound(Exception):
    """文号/section 不存在（框架页）——负结果，不计 source_failure。"""


# ------------------------------------------------------------ 工具

async def _get(client: httpx.AsyncClient, url: str, *, params=None,
               headers=None, follow_redirects: bool = False):
    """GET + 瞬态重试 1 次。返回 (response, recovered)。"""
    try:
        return await client.get(url, params=params, headers=headers,
                                follow_redirects=follow_redirects), False
    except Exception:  # noqa: BLE001
        await asyncio.sleep(2)
        return await client.get(url, params=params, headers=headers,
                                follow_redirects=follow_redirects), True


def _mk_record(*, evidence_id: str, source_id: str, jurisdiction: str,
               region: str, url: str, title: str, doc_key: str, text: str,
               collector: str, source_role: str, language: str,
               nav_trimmed: int, route: str) -> dict:
    return {
        "evidence_id": evidence_id, "channel": "connector",
        "source_id": source_id, "region": region, "url": url,
        "title": title, "publish_date": "",
        "meta": {"region": region, "jurisdiction": jurisdiction,
                 "doc_key": doc_key, "page_title": "",
                 "nav_trimmed_chars": nav_trimmed, "collector": collector,
                 "language": language, "source_role": source_role,
                 "discovered_by_round_route": route},
        "text": text,
    }


# ------------------------------------------------------------ SE

async def se_search(client, term: str) -> list[dict]:
    """fritext 检索 → [{title, doc}]（search-hit 块：标题 + SFS-nummer）。"""
    r, _ = await _get(client, "https://rkrattsbaser.gov.se/sfst",
                      params={"fritext": term}, headers=UA)
    hits = []
    for m in re.finditer(
            r'<div class="search-hit">.*?<a href="[^"]*">(.*?)</a>.*?'
            r"SFS-nummer:\s*(\d{4}:\d+)", r.text, re.S):
        hits.append({"title": html_mod.unescape(
            re.sub(r"<[^>]+>", "", m.group(1))).strip(),
            "doc": m.group(2)})
    return hits


async def se_fetch(client, doc: str) -> dict | None:
    url = f"https://rkrattsbaser.gov.se/sfst?bet={doc}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 1500:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    year, num = doc.split(":")
    return _mk_record(
        evidence_id=f"se_sfst_{doc.replace(':', '_')}", source_id="se_sfst",
        jurisdiction="SE", region="EU", url=url,
        title=f"SFS {doc}", doc_key=f"SE:SFS:{doc}", text=body[:60000],
        collector="jurisdiction_round", source_role="MS_LEGISLATION_DATABASE",
        language="sv", nav_trimmed=nav, route="")


# ------------------------------------------------------------ FI

async def fi_search(client, term: str) -> list[dict]:
    """haku 检索 → 链接 /fi/lainsaadanto/YYYY/NNN → {doc=YYYYNNNN}。"""
    r, _ = await _get(client, "https://www.finlex.fi/fi/haku",
                      params={"q": term}, headers=UA)
    text = r.text + ("\n" + (extract_next_flight(r.text) or ""))
    out, seen = [], set()
    for year, num in re.findall(
            r"/fi/lainsaadanto/(\d{4})/(\d+)(?![\d\-])", text):
        if (year, num) in seen:
            continue
        seen.add((year, num))
        out.append({"doc": f"{year}{int(num):04d}", "year": year, "num": num})
    return out


async def fi_fetch(client, doc: str) -> dict | None:
    year = doc[:4]
    url = f"https://www.finlex.fi/fi/laki/ajantasa/{year}/{doc}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    flight = extract_next_flight(r.text)
    nodes = extract_text_nodes(flight) if flight else ""
    if len(nodes) >= 2000:
        text = nodes
    elif flight:
        text = strip_html(flight)
    else:
        text = strip_html(r.text)
    if len(text) < 2000:
        raise DocNotFound(f"skeleton_or_empty({len(text)} chars)")
    body, nav = trim_nav(text)
    num = str(int(doc[4:]))
    return _mk_record(
        evidence_id=f"fi_finlex_{doc}", source_id="fi_finlex",
        jurisdiction="FI", region="EU", url=url,
        title=f"SDK {num}/{year}", doc_key=f"FI:SDK:{year}/{num}",
        text=body[:60000], collector="jurisdiction_round",
        source_role="MS_LEGISLATION_DATABASE", language="fi",
        nav_trimmed=nav, route="")


# ------------------------------------------------------------ US-CA

async def ca_fetch(client, doc: str) -> dict | None:
    """doc = 'PRC:42451' 或 'PRC:42451.5'。"""
    law_code, section = doc.split(":", 1)
    url = ("https://leginfo.legislature.ca.gov/faces/"
           f"codes_displaySection.xhtml?lawCode={law_code}"
           f"&sectionNum={section}")
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 800:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    return _mk_record(
        evidence_id=f"us_ca_leginfo_{section.replace('.', '_')}",
        source_id="us_ca_leginfo", jurisdiction="US-CA", region="US",
        url=url, title=f"CA {law_code} Code Section {section}",
        doc_key=f"US-CA:{law_code}:{section}", text=body[:60000],
        collector="jurisdiction_round", source_role="STATE_STATUTES",
        language="en", nav_trimmed=nav, route="")


# ------------------------------------------------------------ US-WA

async def wa_fetch(client, cite: str) -> dict | None:
    url = f"https://app.leg.wa.gov/RCW/default.aspx?cite={cite}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 800:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    return _mk_record(
        evidence_id=f"us_wa_rcw_{cite.replace('.', '_').lower()}",
        source_id="us_wa_rcw", jurisdiction="US-WA", region="US",
        url=url, title=f"RCW {cite}", doc_key=f"US-WA:RCW:{cite}",
        text=body[:60000], collector="jurisdiction_round",
        source_role="STATE_STATUTES", language="en",
        nav_trimmed=nav, route="")


# ------------------------------------------------------------ CZ（MODE B 批次 1）

#: B 词年索引扫描窗口（与 A 种子年代互补；2026-09-15 定）
#: Batch 1C V2：扩窗 2001–2026（语料生产轮；V2 plan 同步记录）
CZ_SCAN_YEARS = tuple(range(2001, 2027))


async def cz_search(client, term: str) -> list[dict]:
    """sbirka.sqw 年索引标题域检索：锚点（N/YYYY）后随标题文本。"""
    hits, seen = [], set()
    tl = term.lower()
    pat = re.compile(r'sbirka\.sqw\?cz=(\d+)&(?:amp;)?r=(\d+)"[^>]*>'
                     r'\s*\d+/\d+\s*</a>(.{0,400})', re.S)
    for y in CZ_SCAN_YEARS:
        r, _ = await _get(client, "https://www.psp.cz/sqw/sbirka.sqw",
                          params={"r": str(y)}, headers=UA)
        for m in pat.finditer(r.text):
            if m.group(2) != str(y):
                continue
            tail = html_mod.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))
            tail = re.sub(r"\s+", " ", tail)
            if tl in tail.lower():
                doc = f"{int(m.group(1))}/{y}"
                if doc not in seen:
                    seen.add(doc)
                    hits.append({"doc": doc, "title": tail.strip()[:120]})
    return hits


async def cz_fetch(client, doc: str) -> dict | None:
    num, year = doc.split("/")
    url = f"https://www.psp.cz/sqw/sbirka.sqw?cz={int(num)}&r={year}"
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    body, nav = trim_nav(strip_html(r.text))
    if len(body) < 800:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    mt = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S)
    title = (html_mod.unescape(re.sub(r"\s+", " ", mt.group(1))).strip()
             if mt else f"{int(num)}/{year} Sb.")
    return _mk_record(
        evidence_id=f"cz_psp_{int(num)}_{year}", source_id="cz_psp",
        jurisdiction="CZ", region="EU", url=url, title=title[:140],
        doc_key=f"CZ:SB:{int(num)}/{year}", text=body[:60000],
        collector="jurisdiction_round", source_role="CZ_NATIONAL_LEGISLATION",
        language="cs", nav_trimmed=nav, route="")


# ------------------------------------------------------------ IT（MODE B 批次 1）

IT_URN_BASE = "https://www.normattiva.it/uri-res/N2Ls?"
#: A 种子解析表（URN 经 Round 1 实测；code 经 Round 9 atto 详情实测）
IT_SEED_TARGETS = {
    "D.Lgs. 188/2008": "urn:nir:stato:decreto.legislativo:2008-11-20;188",
    "D.Lgs. 152/2006": "urn:nir:stato:decreto.legislativo:2006-04-03;152",
    "D.Lgs. 82/2005": "urn:nir:stato:decreto.legislativo:2005-03-03;82",
    "D.Lgs. 49/2014": "urn:nir:stato:decreto.legislativo:2014-03-14;49",
    "D.Lgs. 118/2020": "code:20G00136;2020-09-12",
    "D.Lgs. 27/2016": "code:16G00035;2016-03-05",
}


def _it_urn_eid(urn: str) -> str:
    m = re.search(r":(\d{4})-(\d{2})-(\d{2});(\d+)$", urn)
    if m:
        return f"it_normattiva_{m.group(4)}_{m.group(1)}"
    return "it_normattiva_" + re.sub(r"\W+", "_", urn)[-48:]


async def it_search(client, term: str) -> list[dict]:
    """veloce 快速检索 → atto 链接（codiceRedazionale + dataPubblicazione）。"""
    r, _ = await _get(client, "https://www.normattiva.it/ricerca/veloce/0",
                      params={"testoRicerca": term}, headers=UA)
    hits, seen = [], set()
    for raw in re.findall(r'href="([^"]*caricaDettaglioAtto[^"]*)"', r.text):
        href = re.sub(r"\s+", "", html_mod.unescape(raw))
        mcode = re.search(r"atto\.codiceRedazionale=([A-Za-z0-9]+)", href)
        mdat = re.search(r"atto\.dataPubblicazioneGazzetta=([0-9\-]+)", href)
        if mcode and mdat:
            doc = f"code:{mcode.group(1)};{mdat.group(1)}"
            if doc not in seen:
                seen.add(doc)
                hits.append({"doc": doc})
    return hits


async def it_fetch(client, doc: str) -> dict | None:
    target = IT_SEED_TARGETS.get(doc, doc)
    if target.startswith("urn:"):
        urn = target
        url = IT_URN_BASE + urn
        eid = _it_urn_eid(urn)
    elif target.startswith("code:"):
        code, data = target[5:].split(";", 1)
        url = ("https://www.normattiva.it/atto/caricaDettaglioAtto"
               f"?atto.dataPubblicazioneGazzetta={data}"
               f"&atto.codiceRedazionale={code}")
        eid = f"it_normattiva_{code.lower()}"
    else:
        raise ValueError(f"IT doc 形式非法：{doc!r}")
    r, _ = await _get(client, url, headers=UA)
    if detect_challenge(r.text):
        raise RuntimeError("challenge_page")
    mt = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.S)
    title = (html_mod.unescape(re.sub(r"\s+", " ", mt.group(1))).strip()
             if mt else doc)
    title = title.replace(" - Normattiva", "").strip()
    body, nav = trim_nav(strip_html(r.text))
    # 门户菜单修剪：正文从「Attuazione…／Art. 1／共和国总统」起截（导航 ~1.5K 字符）
    cut = None
    for pat in (r"\bAttuazione\s+della\s+direttiva",
                r"\bArt(?:icolo)?\.?\s*1\b",
                r"\bIL\s+PRESIDENTE\s+DELLA\s+REPUBBLICA\b"):
        m = re.search(pat, body)
        if m and (cut is None or m.start() < cut):
            cut = m.start()
    if cut and cut > 100:
        body = body[cut:]
    # 页脚修剪（Privacy/Cookie・Note legali・Mappa/FAQ 链接区 —— 防 FAQ 闸门误伤）
    for tail in (r"Privacy\s+e\s+Cookie", r"Note\s+legali",
                 r"Mappa\s+del\s+sito"):
        mt2 = re.search(tail, body)
        if mt2:
            body = body[:mt2.start()]
            break
    body = title + ". " + body
    if len(body) < 800:
        raise DocNotFound(f"skeleton_or_empty({len(body)} chars)")
    return _mk_record(
        evidence_id=eid, source_id="it_normattiva",
        jurisdiction="IT", region="EU", url=url, title=title[:140],
        doc_key=f"IT:NIR:{urn if target.startswith('urn:') else target}",
        text=body[:60000], collector="jurisdiction_round",
        source_role="IT_NATIONAL_LEGISLATION", language="it",
        nav_trimmed=nav, route="")


# ------------------------------------------------------------ HU（MODE B 批次 1）


async def hu_search(client, term: str) -> list[dict]:
    """?content= 内容检索（真过滤参数；V2：3 页/词）→ 文档 sha。"""
    hits, seen = [], set()
    for page in (1, 2, 3):
        params = {"content": term}
        if page > 1:
            params["page"] = str(page)
        r, _ = await _get(client, "https://magyarkozlony.hu",
                          params=params, headers=UA)
        for sha in re.findall(r"dokumentumok/([0-9a-f]{40})", r.text):
            if sha not in seen:
                seen.add(sha)
                hits.append({"doc": sha})
    return hits


async def hu_fetch(client, doc: str) -> dict | None:
    label = ""
    if re.fullmatch(r"[0-9a-f]{40}", doc):
        sha = doc
    else:
        m = re.fullmatch(r"(\d{4})/(\d+)", doc)
        if not m:
            raise DocNotFound(f"hu doc 形式非法：{doc}")
        year, serial = m.group(1), m.group(2)
        rp, _ = await _get(client, "https://magyarkozlony.hu",
                           params={"year": year, "serial": serial},
                           headers=UA)
        shas = list(dict.fromkeys(
            re.findall(r"dokumentumok/([0-9a-f]{40})", rp.text)))
        if not shas:
            raise DocNotFound(f"issue {doc} 未解析出文档")
        sha = shas[0]
        label = f"{year}. évi {serial}. szám — "
    url = f"https://magyarkozlony.hu/dokumentumok/{sha}/letoltes"
    r, _ = await _get(client, url, headers=UA)
    if r.content[:4] != b"%PDF":
        raise DocNotFound(f"not_pdf({len(r.content)}B)")
    import io as _io

    from pypdf import PdfReader
    reader = PdfReader(_io.BytesIO(r.content))
    pages = min(len(reader.pages), 40)
    text = "\n".join((reader.pages[i].extract_text() or "")
                     for i in range(pages))
    head = " ".join(text[:200].split())
    return _mk_record(
        evidence_id=f"hu_mk_{sha}", source_id="hu_magyarkozlony",
        jurisdiction="HU", region="EU",
        url=f"https://magyarkozlony.hu/dokumentumok/{sha}/megtekintes",
        title=(label + head)[:140], doc_key=f"HU:MK:{sha}",
        text=text[:60000], collector="jurisdiction_round",
        source_role="HU_OFFICIAL_GAZETTE", language="hu",
        nav_trimmed=0, route="")


# ------------------------------------------------------------ SK（MODE B 批次 1）

#: B 词年索引扫描窗口（每页含全年 450 部法标题——Round 10 实测）
SK_SCAN_YEARS = tuple(range(2012, 2027))


async def sk_search(client, term: str) -> list[dict]:
    """静态年索引标题域检索（锚文本含法律标题）。"""
    hits, seen = [], set()
    tl = term.lower()
    for y in SK_SCAN_YEARS:
        r, _ = await _get(client,
                          f"https://static.slov-lex.sk/static/SK/ZZ/{y}/",
                          headers=UA)
        for m in re.finditer(r'<a[^>]*href="(\d{1,4})/"[^>]*>(.*?)</a>',
                             r.text, re.S):
            title = html_mod.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))
            title = re.sub(r"\s+", " ", title).strip()
            if tl in title.lower():
                doc = f"{int(m.group(1))}/{y}"
                if doc not in seen:
                    seen.add(doc)
                    hits.append({"doc": doc, "title": title[:120]})
    return hits


async def sk_fetch(client, doc: str) -> dict | None:
    num, year = doc.split("/")
    n = int(num)

    def _sk_title(text: str) -> str:
        m = re.search(r"(\d{1,4})\s+"
                      r"(ZÁKON|VYHLÁŠKA|NARIADENIE VLÁDY|NARIADENIE|OZNÁMENIE|"
                      r"ÚSTAVNÝ ZÁKON)", text)
        if m:
            seg = re.sub(r"\s+", " ",
                         text[m.start():m.start() + 260]).strip()
            return seg[:220]
        return f"{n}/{year} Z. z."

    # 1) PDF 优先：静态 HTML 多为"骨架目录"（无正文句子 → 分类窗口
    #    NO_THEME）；PDF 为公报正式文本（含完整句子与标题行）
    pdf_url = (f"https://www.slov-lex.sk/static/pdf/{year}/{n}/"
               f"ZZ_{year}_{n}.pdf")
    rp, _ = await _get(client, pdf_url, headers=UA, follow_redirects=True)
    if rp.content[:4] == b"%PDF":
        import io as _io

        from pypdf import PdfReader
        reader = PdfReader(_io.BytesIO(rp.content))
        pages = min(len(reader.pages), 60)
        text = "\n".join((reader.pages[i].extract_text() or "")
                         for i in range(pages))
        if len(text) >= 2000:
            return _mk_record(
                evidence_id=f"sk_slovlex_{n}_{year}", source_id="sk_slovlex",
                jurisdiction="SK", region="EU", url=pdf_url,
                title=_sk_title(text), doc_key=f"SK:ZZ:{n}/{year}",
                text=text[:60000], collector="jurisdiction_round",
                source_role="SK_NATIONAL_LEGISLATION", language="sk",
                nav_trimmed=0, route="")
    # 2) HTML 回退（骨架目录，仅当 PDF 不可得）
    html_url = ("https://static.slov-lex.sk/static/SK/ZZ/"
                f"{year}/{n}/vyhlasene_znenie.html")
    r, _ = await _get(client, html_url, headers=UA)
    if r.status_code == 200 and len(r.content) > 3000:
        body, nav = trim_nav(strip_html(r.text))
        if len(body) >= 2000:
            return _mk_record(
                evidence_id=f"sk_slovlex_{n}_{year}", source_id="sk_slovlex",
                jurisdiction="SK", region="EU", url=html_url,
                title=f"{n}/{year} Z. z.", doc_key=f"SK:ZZ:{n}/{year}",
                text=body[:60000], collector="jurisdiction_round",
                source_role="SK_NATIONAL_LEGISLATION", language="sk",
                nav_trimmed=nav, route="")
    raise DocNotFound(f"no_pdf_or_html({doc})")


# ------------------------------------------------------------ AT（MODE B 批次 1C：OGD 通道）
AT_API = ("https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
          "?Applikation=BrKons&Suchworte={q}&Seitennummer={p}")
_AT_NOR_RE = re.compile(r"(NOR\d+)")


def _at_walk(obj, key):
    out: list = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out += _at_walk(v, key)
    elif isinstance(obj, list):
        for x in obj:
            out += _at_walk(x, key)
    return out


def _at_iter_nodes(obj):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _at_iter_nodes(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _at_iter_nodes(x)


async def at_search(client, term: str) -> list[dict]:
    """RIS OGD API 检索（data.bka.gv.at）：Kurztitel + DokumentUrl → NOR。"""
    hits, seen = [], set()
    for page in (1, 2):
        r, _ = await _get(client, AT_API.format(q=term, p=page), headers=UA)
        if r.status_code != 200:
            continue
        try:
            data = r.json()
        except Exception:  # noqa: BLE001
            continue
        kurztitel = _at_walk(data, "Kurztitel")
        urls = [u["DokumentUrl"] for u in _at_iter_nodes(data)
                if isinstance(u.get("DokumentUrl"), str)]
        for i, t in enumerate(kurztitel):
            u = urls[i] if i < len(urls) else ""
            m = _AT_NOR_RE.search(u or "")
            if not m:
                continue
            nor = m.group(1)
            if nor in seen:
                continue
            seen.add(nor)
            hits.append({"doc": nor, "title": str(t)[:120]})
    return hits


async def at_fetch(client, doc: str) -> dict | None:
    """OGD 文档直取：ogd.ris.bka.gv.at/Dokumente/Bundesnormen/{NOR}.html。"""
    m0 = _AT_NOR_RE.search(doc)
    nor = m0.group(1) if m0 else doc
    url = (f"https://ogd.ris.bka.gv.at/Dokumente/Bundesnormen/"
           f"{nor}/{nor}.html")
    r, _ = await _get(client, url, headers=UA)
    if r.status_code != 200 or len(r.content) < 2000:
        raise DocNotFound(f"at_ogd_http({r.status_code})")
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", r.text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 1500:
        raise DocNotFound(f"skeleton_or_empty({len(text)} chars)")
    m = re.search(r"Kurztitel\s+(.+?)\s+Kundmachungsorgan", text)
    ttl = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    title = f"{ttl}（{nor}）" if ttl else nor
    return _mk_record(
        evidence_id=f"at_ogd_{nor}", source_id="at_ris_ogd",
        jurisdiction="AT", region="EU", url=url,
        title=title[:200], doc_key=f"AT:OGD:{nor}",
        text=text[:60000], collector="jurisdiction_round",
        source_role="AT_NATIONAL_LEGISLATION", language="de",
        nav_trimmed=0, route="")


# ------------------------------------------------------------ 引用抽取（C）

CITE_PATTERNS = {
    "SE": re.compile(r"SFS\s*(\d{4}:\d+)"),
    "FI": re.compile(r"(\d{1,4})/(\d{4})"),
    "US-CA": re.compile(r"Section\s+(\d{4,5}(?:\.\d+)?)\s+of\s+the\s+Public\s+Resources\s+Code", re.I),
    "US-WA": re.compile(r"RCW\s+(\d+A\.\d+\.\d+)"),
    # Batch 1C：CZ/SK 引用扩张（N/YYYY 文号 → 官方直链文档格式）
    "CZ": re.compile(r"(\d{1,4})/(\d{4})\s*Sb\."),
    "SK": re.compile(r"(\d{1,4})/(\d{4})\s*Z\.\s?z\."),
}


def _cite_to_doc(jid: str, m: re.Match) -> str:
    if jid == "SE":
        return m.group(1)
    if jid == "FI":
        num, year = int(m.group(1)), m.group(2)
        return f"{year}{num:04d}"
    if jid == "US-CA":
        return f"PRC:{m.group(1)}"
    if jid in ("CZ", "SK"):
        return f"{int(m.group(1))}/{m.group(2)}"
    return m.group(1)


def _extract_cited(jid: str, records: list[dict], existing: set[str]) -> list[str]:
    """从**自有记录**（meta.jurisdiction == jid）正文抽引用；
    跳过 NIM 元数据摘要（噪声源：文献摘要含大量年代号）。"""
    pat = CITE_PATTERNS[jid]
    docs, seen = [], set()
    for r in records:
        if (r.get("meta") or {}).get("jurisdiction") != jid:
            continue
        text = (r.get("title") or "") + "\n" + (r.get("text") or "")[:20000]
        for m in pat.finditer(text):
            doc = _cite_to_doc(jid, m)
            if doc in seen:
                continue
            seen.add(doc)
            docs.append(doc)
    return docs


# ------------------------------------------------------------ 轮执行

FETCHERS = {"SE": se_fetch, "FI": fi_fetch, "US-CA": ca_fetch,
            "US-WA": wa_fetch, "CZ": cz_fetch, "IT": it_fetch,
            "HU": hu_fetch, "SK": sk_fetch, "AT": at_fetch}
SEARCHERS = {"SE": se_search, "FI": fi_search,
             "CZ": cz_search, "IT": it_search, "HU": hu_search,
             "SK": sk_search, "AT": at_search}


def _eid_for(jid: str, doc: str) -> str:
    """路线 B 预去重用的 evidence_id 推算（须与 Fetchers 产物一致）。"""
    if jid == "SE":
        return f"se_sfst_{doc.replace(':', '_')}"
    if jid == "FI":
        return f"fi_finlex_{doc}"
    if jid == "CZ":
        return f"cz_psp_{doc.replace('/', '_')}"
    if jid == "IT":
        if doc.startswith("code:"):
            return f"it_normattiva_{doc[5:].split(';')[0].lower()}"
        return _it_urn_eid(doc)
    if jid == "HU":
        return f"hu_mk_{doc}"
    if jid == "SK":
        return f"sk_slovlex_{doc.replace('/', '_')}"
    if jid == "AT":
        return f"at_ogd_{doc}"
    if jid == "US-CA":
        return f"us_ca_leginfo_{doc.split(':')[-1].replace('.', '_')}"
    if jid == "US-WA":
        return f"us_wa_rcw_{doc.replace('.', '_').lower()}"
    return f"{jid.lower()}_{doc}"


async def _run_route_a(client, jid, plan, existing) -> RouteResult:
    rr = RouteResult("A", "official_enumeration")
    nf: list[dict] = []
    seeds = list(plan.query_set.fr_agencies)
    for seed in seeds:
        rr.queries.append(seed)
        eid_guess = None   # 由 fetcher 决定
        try:
            rec = await FETCHERS[jid](client, seed)
        except DocNotFound as exc:
            nf.append({"query": seed, "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_leg",
                                       "query": seed,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_leg"] = \
            rr.source_success.get(f"{jid.lower()}_leg", 0) + 1
        rr.raw_found += 1
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "A"
        eid_guess = rec["evidence_id"]
        if eid_guess not in existing:
            rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def _run_route_b(client, jid, plan, existing, max_fetch) -> RouteResult:
    rr = RouteResult("B", "native_fulltext_search")
    nf: list[dict] = []
    searcher = SEARCHERS.get(jid)
    if searcher is None:
        rr.source_failures.append({
            "source": f"{jid.lower()}_search",
            "failure": "no_search_endpoint（如实记录，通道缺失）"})
        return rr
    wanted: dict[str, dict] = {}
    for term in plan.query_set.fr_terms:
        rr.queries.append(term)
        try:
            hits = await searcher(client, term)
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_search",
                                       "query": term,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_search"] = \
            rr.source_success.get(f"{jid.lower()}_search", 0) + 1
        rr.raw_found += len(hits)
        for h in hits:
            doc = h["doc"]
            eid = _eid_for(jid, doc)
            if eid in existing or eid in wanted:
                continue
            wanted[eid] = h
    fetched = 0
    for eid, h in list(wanted.items())[:max_fetch]:
        fetched += 1
        try:
            rec = await FETCHERS[jid](client, h["doc"])
        except DocNotFound as exc:
            nf.append({"query": h["doc"], "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_doc",
                                       "query": h["doc"],
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "B"
        rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def _run_route_c(client, jid, plan, existing, records,
                       max_fetch) -> RouteResult:
    rr = RouteResult("C", "legal_relation_expansion")
    nf: list[dict] = []
    seeds: list[str] = []
    # 显式引用种子（plan.eu_keywords 解析为文号）
    for kw in plan.query_set.eu_keywords:
        m = CITE_PATTERNS[jid].search(kw.replace("SDK ", "").replace("SFS ", ""))
        if m:
            seeds.append(_cite_to_doc(jid, m))
        else:
            # 形如 "RCW 70A.555.010" / "PRC Section 42451" 的通用模式
            m2 = re.search(r"(?:\d{1,4}/\d{4})|(?:\d{4}:\d+)|"
                           r"(?:\d+A\.\d+\.\d+)|(?:\d{4,5}(?:\.\d+)?)", kw)
            if m2:
                tok = m2.group(0)
                if jid == "US-CA":
                    seeds.append(f"PRC:{tok}")
                else:
                    seeds.append(tok)
    # 运行时引用抽取（语料正文）
    seeds += _extract_cited(jid, records, existing)
    seen = set()
    fetched = 0
    for doc in seeds:
        if doc in seen:
            continue
        seen.add(doc)
        eid = _eid_for(jid, doc)
        if eid in existing:
            continue
        if fetched >= max_fetch:
            break
        fetched += 1
        rr.queries.append(doc)
        try:
            rec = await FETCHERS[jid](client, doc)
        except DocNotFound as exc:
            nf.append({"query": doc, "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_cite",
                                       "query": doc,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_cite"] = \
            rr.source_success.get(f"{jid.lower()}_cite", 0) + 1
        rr.raw_found += 1
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "C"
        rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def _run_route_d(client, jid, plan, existing, max_fetch) -> RouteResult:
    rr = RouteResult("D", "gap_discovery")
    nf: list[dict] = []
    seeds = list(plan.query_set.cross_terms)
    if not seeds:
        rr.not_found = nf  # type: ignore[attr-defined]
        return rr
    fetched = 0
    for seed in seeds[:max_fetch]:
        fetched += 1
        rr.queries.append(seed)
        try:
            rec = await FETCHERS[jid](client, seed)
        except DocNotFound as exc:
            nf.append({"query": seed, "reason": str(exc)[:100]})
            continue
        except Exception as exc:  # noqa: BLE001
            rr.source_failures.append({"source": f"{jid.lower()}_gap",
                                       "query": seed,
                                       "failure": (type(exc).__name__ + ": "
                                                   + str(exc))[:160]})
            continue
        rr.source_success[f"{jid.lower()}_gap"] = \
            rr.source_success.get(f"{jid.lower()}_gap", 0) + 1
        rr.raw_found += 1
        if rec is None:
            continue
        rec["meta"]["discovered_by_round_route"] = "D"
        rr.candidates.append(rec)
    rr.not_found = nf  # type: ignore[attr-defined]
    return rr


async def run_round(jid: str, round_no: int, plan, mode: str,
                    *, persist: bool = True, max_fetch: int = 40) -> dict:
    records = load_records(ROOT)
    existing = {str(r.get("evidence_id")) for r in records}
    started = now_iso()
    routes = list(plan.discovery_routes)
    results: list[RouteResult] = []
    async with httpx.AsyncClient(headers=UA, timeout=45,
                                 follow_redirects=True) as client:
        for r in routes:
            if r == "A":
                results.append(await _run_route_a(client, jid, plan, existing))
            elif r == "B":
                results.append(await _run_route_b(client, jid, plan, existing,
                                                  max_fetch))
            elif r == "C":
                results.append(await _run_route_c(client, jid, plan, existing,
                                                  records, max_fetch))
            elif r == "D":
                results.append(await _run_route_d(client, jid, plan, existing,
                                                  max_fetch))

    classified: dict[str, str] = {}
    topics_by_id: dict[str, list[str]] = {}
    all_candidates: dict[str, dict] = {}
    for rr in results:
        for c in rr.candidates:
            all_candidates.setdefault(c["evidence_id"], c)
    for eid, rec in all_candidates.items():
        try:
            res = classify_record(rec)
            classified[eid] = res.classification
            if res.topic_ids:
                topics_by_id[eid] = list(res.topic_ids)
        except Exception:  # noqa: BLE001
            classified[eid] = "D"
    route_dicts = [rr.as_dict(classified=classified, existing_ids=existing,
                              topics_by_id=topics_by_id) for rr in results]
    for d, rr in zip(route_dicts, results):
        d["not_found"] = getattr(rr, "not_found", [])

    failures = [f for r in route_dicts for f in (r.get("source_failures") or [])]
    success: dict[str, int] = {}
    for r in route_dicts:
        for src, n in (r.get("source_success") or {}).items():
            success[src] = success.get(src, 0) + int(n)
    critical = set(plan.critical_sources)
    crit_fail_no_success = any(
        (f.get("source") in critical) and success.get(f.get("source"), 0) == 0
        for f in failures)
    validity = derive_validity(failures=len(failures),
                               critical_failed_no_success=crit_fail_no_success)
    round_id = f"{jid}-R{round_no}-{now_iso()[:10]}"
    record = build_round_record(
        round_id=round_id, scope=jid, started_at=started, ended_at=now_iso(),
        routes=route_dicts,
        source_roles=[pr.role for pr in plan.source_roles],
        plan_id=plan.plan_id, plan_hash=plan.plan_hash(),
        round_mode=("discovery_expansion" if mode == "discovery"
                    else "convergence_validation"),
        validity=validity,
        transient_failures=sum(int(r.get("transient_recovered", 0) or 0)
                               for r in route_dicts), notes="")
    ROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    ts = now_iso().replace(":", "").replace("-", "")[:15]
    fp = ROUNDS_DIR / f"round_{jid}_{round_no}_{ts}.json"
    fp.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                  encoding="utf-8")

    persisted = 0
    if persist:
        fresh = []
        for eid, rec in all_candidates.items():
            cls = classified.get(eid, "D")
            if eid in existing or cls not in ACCEPTED_CLASSES:
                continue
            out_rec = dict(rec)
            out_rec["relevant"] = cls in ("A1", "A2", "B")
            out_rec["relevance_score"] = out_rec.get("relevance_score", 0.0)
            meta = dict(out_rec.get("meta") or {})
            meta["acceptance_class"] = cls
            meta["discovered_by_round"] = round_id
            out_rec["meta"] = meta
            out_rec.setdefault("channel", "connector")
            fresh.append(out_rec)
        if fresh:
            corpus_fp = ROOT / "outputs" / f"round_{jid}_{round_no}_{ts}.jsonl"
            with corpus_fp.open("w", encoding="utf-8") as f:
                for r in fresh:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            persisted = len(fresh)
            record["persisted_documents"] = persisted
            record["persisted_file"] = corpus_fp.name
            fp.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                          encoding="utf-8")

    # 索引更新（与联邦轮同一视图）
    rebuild_round_index()
    return record


def rebuild_round_index() -> dict:
    """重建 outputs/audit/discovery_rounds.json（可独立调用）。

    索引条目含 route_ids（独立路线类别——eligibility 判定输入），
    并保持 plan_convergence 的同-plan 子集 streak 口径。
    """
    rounds: list[dict] = []
    for idx_fp in sorted(glob.glob(str(ROUNDS_DIR / "round_*.json"))):
        try:
            data = json.loads(Path(idx_fp).read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        entry = {k: data.get(k) for k in
                 ("round_id", "scope_level", "accepted_novelty_rate",
                  "raw_yield", "totals", "ended_at", "plan_id",
                  "plan_hash", "round_mode", "round_validity")}
        entry["route_ids"] = [str(r.get("id") or "")
                              for r in (data.get("routes") or [])]
        rounds.append(entry)
    plan_conv: dict[str, dict] = {}
    for h in sorted({r.get("plan_hash") for r in rounds if r.get("plan_hash")}):
        # 多管辖地并行：streak 只在**同 plan_hash 的轮次子集**内判定
        # （不同管辖地/不同 plan 的轮不得交错截断彼此的 streak）
        subset = [r for r in rounds if r.get("plan_hash") == h]
        plan_conv[h[:12]] = convergence_status(
            subset, plan_hash=h, mode_required="convergence_validation")
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps({
        "generated_at": now_iso(), "rounds": rounds,
        "convergence": convergence_status(rounds),
        "plan_convergence": plan_conv}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    return {"rounds": len(rounds), "plans": len(plan_conv)}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="")
    ap.add_argument("--mode", default="discovery",
                    choices=["discovery", "validation"])
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--max-fetch", type=int, default=40)
    ap.add_argument("--no-persist", action="store_true")
    ap.add_argument("--show", action="store_true")
    args = ap.parse_args()

    if args.show:
        if INDEX.exists():
            data = json.loads(INDEX.read_text(encoding="utf-8"))
            print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        else:
            print("（尚无轮次索引）")
        return 0

    if not args.plan:
        print("❌ 管辖地轮必须 --plan <PLAN_ID>（如 SE_PLAN_V1）")
        return 2
    plan = load_plan(args.plan)
    for w in validate_plan(plan):
        print(f"  ⚠ {w}")
    jid = plan.jurisdiction
    if jid not in SUPPORTED:
        print(f"❌ 管辖地 {jid} 通道未适配（支持：{SUPPORTED}）——如实拒绝执行")
        return 2
    if plan.scope != jid:
        print(f"❌ 管辖地轮要求 scope == jurisdiction（{plan.scope} vs {jid}）")
        return 2
    print(f"▸ plan={plan.plan_id} hash={plan.plan_hash()[:12]} "
          f"jid={jid} mode={args.mode} routes={plan.discovery_routes}")
    record = await run_round(jid, args.round, plan, args.mode,
                             persist=not args.no_persist,
                             max_fetch=args.max_fetch)
    t = record["totals"]
    print(f"=== Round {record['round_id']} ===")
    print(f"  mode={record.get('round_mode')} "
          f"validity={record.get('round_validity')}")
    for r in record["routes"]:
        print(f"  [{r['id']}] {r['name']:26s} raw={r['raw_found']:4d} "
              f"uniq={r['unique_candidate_count']:4d} "
              f"new={r['new_unique_accepted_count']:3d} "
              f"dup={r['duplicate_accepted_count']:3d} "
              f"rej={r['rejected_count']:3d} fail={len(r['source_failures'])} "
              f"notfound={len(r.get('not_found') or [])} "
              f"｜ cls={r['accepted_by_class']}")
    print(f"  TOTAL raw={t['raw_found']} new_acc={t['new_unique_accepted_count']} "
          f"dup_acc={t['duplicate_accepted_count']} "
          f"failures={t['source_failures']}")
    print(f"  new_by_class={t.get('new_by_class', {})} "
          f"new_high_risk_B={t.get('new_high_risk_B', 0)}")
    print(f"  persisted={record.get('persisted_documents', 0)} → "
          f"{record.get('persisted_file', '（未写）')}")
    print(f"  raw_yield={record['raw_yield']}  ｜ accepted_novelty_rate="
          f"{record['accepted_novelty_rate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
