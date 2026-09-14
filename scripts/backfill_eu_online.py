# -*- coding: utf-8 -*-
"""backfill_eu_online.py —— EU 占位在线回填（Phase 4B-2B1 §5，P0 主体）。

读 outputs/audit/content_completeness.json 的 EU P0 缺口 → 经 eur_lex
connector fetch_fulltext 逐条抓取 → 落盘 sources/eurlex-fulltext/*.txt →
原地合并到 outputs 记录。

失败处理（不掩盖）：
  · EUR-Lex 202/站点降级 → meta.content_state="FETCH_FAILED" + failure_reason
  · 成功但 <600 字符（更正件类短文书）→ meta.short_instrument=True
重试：--rounds N（默认 2），每轮间隔 --sleep 秒（默认 20）。

用法：py scripts/backfill_eu_online.py [--rounds 2] [--sleep 20]
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

FULLTEXT_DIR = ROOT / "sources" / "eurlex-fulltext"
OUTPUTS = ROOT / "outputs"
TEXT_CAP = 400_000

# ── CELLAR 官方 content-negotiation（Publications Office REST）──────────
# EUR-Lex 站点（eur-lex.europa.eu）对高密度请求启用 202 软风控；其内容后端
# CELLAR 提供官方机器接口（publications.europa.eu/resource/celex/{ID}），
# 按 Accept 类型返回 XHTML / Formex XML / PDF（2B1R 恢复取证：二者均官方）。
CELLAR_BASE = "http://publications.europa.eu/resource/celex/"
CELLAR_LANG = "eng"
CELLAR_INTERVAL = 5.0
CELLAR_ACCEPT_XHTML = "application/xhtml+xml"
CELLAR_ACCEPT_FORMEX = "application/xml;notice=object"
CELLAR_ACCEPT_PDF = "application/pdf"


def _eu_gap_list() -> list[tuple[str, str]]:
    """→ [(celex, acceptance_class)]，**A2 优先 → B → 其余**（2B1R §3）。"""
    fp = OUTPUTS / "audit" / "content_completeness.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    rows = []
    for x in d["backfill_queue"]:
        if x["backfill_status"] != "P0":
            continue
        eid = x["evidence_id"]
        if not eid.startswith("eu_") or eid.startswith(
                ("eu_nim_", "eu_fulltext_", "eu_eurlex_", "eu_cellar_")):
            continue
        rows.append((eid[len("eu_"):], x["acceptance_class"]))
    order = {"A1": 0, "A2": 1, "B": 2, "C": 3, "D": 4}
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for celex, cls in sorted(rows, key=lambda r: (order.get(r[1], 9), r[0])):
        if celex not in seen:
            seen.add(celex)
            out.append((celex, cls))
    return out


DEGRADED_MARKERS = ("temporarily not fully available", "under maintenance",
                    "service unavailable", "just a moment",
                    "checking your browser")


def _browser_ua() -> str:
    from app.connectors.base import BROWSER_UA
    return BROWSER_UA


def _clean_html_body(body: str) -> str:
    """HTML/XHTML → 纯文本（与 eur_lex._extract_body 尾部清洗一致）。"""
    import html as _html
    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", body)
    body = re.sub(r"(?s)<!--.*?-->", " ", body)
    body = re.sub(r"(?i)<(br|/p|/div|/tr|/h[1-6]|/li|/td)[^>]*>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = _html.unescape(body).replace("\u00a0", " ")
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n\s*\n+", "\n", body)
    return body.strip()


def _extract_cellar_xhtml(xh: str) -> str:
    """CELLAR OJ XHTML（CONVEX 表单）→ 正文纯文本。

    优先 `eli-container`/`eli-main-title` 容器；否则清理整个 body。
    """
    if not xh:
        return ""
    m = re.search(r'(?is)<div[^>]+class="eli-container"[^>]*>(.*)</div>\s*</body>', xh)
    if m and len(m.group(1)) > 3000:
        return _clean_html_body(m.group(1))
    m = re.search(r"(?is)<body[^>]*>(.*)</body>", xh)
    body = m.group(1) if m else xh
    return _clean_html_body(body)


def _extract_formex(xml_text: str) -> str:
    """Formex XML → 正文纯文本（ENACTING.TERMS 子树优先，否则全树）。"""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""

    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    terms = None
    for el in root.iter():
        if _local(el.tag).upper().startswith("ENACTING"):
            terms = el
            break
    target = terms if terms is not None else root
    chunks: list[str] = []
    for node in target.iter():
        if node.text and node.text.strip():
            chunks.append(node.text.strip())
    text = "\n".join(chunks)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = text.strip()
    # manifest 防护：URI 清单（CELLAR notice=object 响应）不是正文
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if lines:
        url_like = sum(1 for ln in lines
                       if "http" in ln or ln.endswith(".ENG")
                       or ln.endswith(".fmx4") or ln.endswith(".pdfa1a"))
        if url_like > max(3, int(len(lines) * 0.3)):
            return ""
    return text


def _extract_pdf(data: bytes) -> str:
    """PDF → 纯文本（pypdf，与 backfill_basel_gaps 同法）。"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
    except Exception:  # noqa: BLE001
        return ""
    pages = []
    for pg in reader.pages[:80]:
        try:
            pages.append(pg.extract_text() or "")
        except Exception:  # noqa: BLE001
            pages.append("")
    text = "\n".join(pages)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


async def _cellar_get(client, url: str, accept: str, retries: int = 1):
    """CELLAR 单请求 + 瞬时故障重试（5xx/传输错误重试一次）。"""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = await client.get(
                url, headers={"User-Agent": _browser_ua(), "Accept": accept,
                              "Accept-Language": CELLAR_LANG},
                timeout=120, follow_redirects=True)
            if resp.status_code in (500, 502, 503, 504) and attempt < retries:
                await asyncio.sleep(8)
                continue
            return resp
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                await asyncio.sleep(8)
                continue
    raise last_exc if last_exc else RuntimeError("cellar_get exhausted")


def _extract_content_uris(manifest_xml: str, suffix: str) -> list[str]:
    """从 CELLAR manifest XML 提取指定后缀的内容 URI（两跳取数）。"""
    uris = re.findall(r"https?://[^\"\s<]+" + re.escape(suffix), manifest_xml)
    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for u in uris:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def _resolve_doc300(client, page_text: str) -> str:
    """300 Multiple-Choice 选择页 → 取 DOC_N 内容流 → 清洗文本。

    新近提案（COM 系）常用此形态：正文 = DOC_1（"1_EN_ACT_*.html"），
    附件 = 其余 DOC。全取并按序拼接，截断到 600K 字符。
    """
    hrefs = re.findall(r'href="(https?://[^"]+/DOC_\d+)"', page_text)
    if not hrefs:
        return ""
    seen: set[str] = set()
    ordered = [h for h in hrefs
               if not (h in seen or seen.add(h))]  # 去重保序
    # DOC_1 优先（正文），其余按序（附件）
    ordered.sort(key=lambda h: 0 if h.endswith("/DOC_1") else 1)
    chunks: list[str] = []
    for u in ordered[:6]:
        try:
            r = await _cellar_get(client, u, "*/*", retries=1)
        except Exception:  # noqa: BLE001
            continue
        await asyncio.sleep(CELLAR_INTERVAL)
        if r.status_code == 200 and len(r.content) > 2000:
            text = _clean_html_body(r.text)
            if text and len(text) > 200:
                chunks.append(text)
    joined = "\n\n".join(chunks)
    return joined[:600_000]


async def _fetch_via_comnat(client, mf_text: str) -> tuple[str, str] | None:
    """深层链：manifest 的 comnat/immc SAMEAS → RDF → manifestation
    (.xhtml/.pdf) 内容流。用于 CELEX xhtml 无变体的新提案。

    comnat 资源：`*/*` 返回 RDF（含 expression_manifested_by_manifestation
    指向 .xhtml/.pdf）；`.xhtml` manifestation 用 `text/html` 取内容，
    `.pdf` 用 `application/pdf` 取 PDF（pypdf 提取）。
    """
    roots = re.findall(
        r"https?://publications\.europa\.eu/resource/(?:comnat|immc)/"
        r"[^\"<\s]+\.[A-Z]{3}", mf_text)
    seen: set[str] = set()
    root_list = [u for u in roots if not (u in seen or seen.add(u))][:2]
    for root in root_list:
        try:
            rd = await _cellar_get(client, root, "*/*", retries=1)
        except Exception:  # noqa: BLE001
            continue
        await asyncio.sleep(CELLAR_INTERVAL)
        if rd.status_code != 200:
            continue
        manifest_uris = re.findall(
            r"https?://publications\.europa\.eu/resource/(?:comnat|immc)/"
            r"[^\"<\s]+\.(?:xhtml|pdf)", rd.text)
        seen2: set[str] = set()
        manifest_uris = [u for u in manifest_uris
                         if not (u in seen2 or seen2.add(u))]
        # .xhtml 优先
        manifest_uris.sort(key=lambda u: 0 if u.endswith(".xhtml") else 1)
        for mu in manifest_uris[:2]:
            accept = ("text/html" if mu.endswith(".xhtml")
                      else "application/pdf")
            try:
                r2 = await _cellar_get(client, mu, accept, retries=1)
            except Exception:  # noqa: BLE001
                continue
            await asyncio.sleep(CELLAR_INTERVAL)
            if r2.status_code != 200 or len(r2.content) < 2000:
                continue
            if mu.endswith(".pdf"):
                text = _extract_pdf(r2.content)
            else:
                text = _clean_html_body(r2.text)
            if text and len(text) >= 150:
                low = text.lower()
                if any(m in low for m in DEGRADED_MARKERS):
                    continue
                return text, ("CELLAR comnat XHTML" if mu.endswith(".xhtml")
                              else "CELLAR comnat PDF")
    return None


async def _fetch_cellar(client, celex: str) -> tuple[str, str] | str:
    """CELLAR 通道链：
    ① XHTML（200→正文；300→DOC_N 解析；瞬断重试）
    ② comnat/immc 深层（manifest→RDF→manifestation 内容流）
    ③ Formex 两跳（manifest→.fmx4）
    ④ PDF 两跳（manifest→.pdfa1a）
    返回 (text, label) 成功；返回 str 为失败原因链。
    """
    url = f"{CELLAR_BASE}{celex}"
    reasons: list[str] = []
    mf_resp = None

    # ① XHTML
    try:
        resp = await _cellar_get(client, url, CELLAR_ACCEPT_XHTML)
    except Exception as exc:  # noqa: BLE001
        resp = None
        reasons.append(f"XHTML:{type(exc).__name__}")
    await asyncio.sleep(CELLAR_INTERVAL)
    if resp is not None:
        if resp.status_code == 200 and len(resp.content) > 2000:
            text = _extract_cellar_xhtml(resp.text)
            if text and len(text) >= 150:
                low = text.lower()
                if not any(m in low for m in DEGRADED_MARKERS):
                    return text, "CELLAR XHTML"
                reasons.append("XHTML:degraded_shell")
            else:
                reasons.append("XHTML:extract_empty")
        elif resp.status_code == 300:
            text = await _resolve_doc300(client, resp.text)
            if text and len(text) >= 150:
                return text, "CELLAR DOC300"
            reasons.append("XHTML:300_no_doc")
        else:
            reasons.append(f"XHTML:{resp.status_code}")

    # ② comnat/immc 深层（需要 manifest）
    try:
        mf_resp = await _cellar_get(client, url, CELLAR_ACCEPT_FORMEX)
    except Exception as exc:  # noqa: BLE001
        mf_resp = None
        reasons.append(f"manifest:{type(exc).__name__}")
    await asyncio.sleep(CELLAR_INTERVAL)
    if mf_resp is not None and mf_resp.status_code == 200:
        got = await _fetch_via_comnat(client, mf_resp.text)
        if got is not None:
            return got
        reasons.append("comnat:no_content")
    elif mf_resp is not None:
        reasons.append(f"manifest:{mf_resp.status_code}")

    # ③ Formex 两跳
    if mf_resp is not None and mf_resp.status_code == 200:
        for u in _extract_content_uris(mf_resp.text, ".fmx4")[:3]:
            try:
                r2 = await _cellar_get(client, u, "application/xml")
            except Exception:  # noqa: BLE001
                continue
            await asyncio.sleep(CELLAR_INTERVAL)
            if r2.status_code == 200 and len(r2.content) > 1500:
                text = _extract_formex(r2.text)
                if text and len(text) >= 150:
                    return text, "CELLAR Formex"
        reasons.append("Formex:no_content")

    # ④ PDF 两跳
    if mf_resp is not None and mf_resp.status_code == 200:
        for u in _extract_content_uris(mf_resp.text, ".pdfa1a")[:2]:
            try:
                r3 = await _cellar_get(client, u, CELLAR_ACCEPT_PDF)
            except Exception:  # noqa: BLE001
                continue
            await asyncio.sleep(CELLAR_INTERVAL)
            if r3.status_code == 200 and len(r3.content) > 1500:
                text = _extract_pdf(r3.content)
                if text and len(text) >= 150:
                    return text, "CELLAR PDF"
        reasons.append("PDF:no_content")

    return "; ".join(reasons) if reasons else "cellar_unknown"


def _merge_bodies(bodies: dict[str, tuple[str, bool, str]],
                  force_ids: frozenset[str] = frozenset()) -> int:
    """celex → (body, short, domain_label) 原地合并（§4：写入验证字段）。

    force_ids 中的记录即使已有正文也强制覆盖（用于修正错误提取的
    Formex-manifest 类污染内容）。返回更新条数。
    """
    import hashlib
    updated = 0
    merged_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review")):
            continue
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        changed = False
        out = []
        for line in lines:
            if not line.strip():
                out.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            eid = str(rec.get("evidence_id") or "")
            if not eid.startswith("eu_") or eid.startswith(
                    ("eu_nim_", "eu_fulltext_", "eu_eurlex_")):
                out.append(line)
                continue
            celex = eid[len("eu_"):]
            hit = bodies.get(celex)
            if not hit:
                out.append(line)
                continue
            body, short, domain_label = hit
            if len(rec.get("text") or "") >= 600 and eid not in force_ids:
                out.append(line)
                continue
            rec["text"] = body[:TEXT_CAP]
            meta = rec.get("meta") or {}
            meta["content_state"] = "FULLTEXT"
            meta["backfilled_from"] = domain_label
            meta["full_chars"] = len(body)
            meta["retrieved_at"] = merged_at
            meta["text_sha256"] = hashlib.sha256(
                body.encode("utf-8")).hexdigest()[:16]
            meta.setdefault("language", "en")
            meta["official_domain"] = ("publications.europa.eu"
                                       if "CELLAR" in domain_label
                                       else "eur-lex.europa.eu")
            # 成功全文不得残留早期失败标记
            meta.pop("failure_reason", None)
            if short:
                meta["short_instrument"] = True
            rec["meta"] = meta
            out.append(json.dumps(rec, ensure_ascii=False))
            changed = True
            updated += 1
        if changed:
            fp.write_text("\n".join(out) + "\n", encoding="utf-8")
    return updated


def _mark_failed(celex: str, reason: str) -> int:
    """失败标记（R(N) 更正件 → METADATA_ONLY + no_online_variant）。"""
    is_corrigendum = "R(" in celex
    marked = 0
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review")):
            continue
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        changed = False
        out = []
        for line in lines:
            if not line.strip():
                out.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            if rec.get("evidence_id") == f"eu_{celex}" and \
                    len(rec.get("text") or "") < 600:
                meta = rec.get("meta") or {}
                if is_corrigendum:
                    meta["content_state"] = "METADATA_ONLY"
                    meta["failure_reason"] = (
                        "no_online_variant: corrigendum has no HTML/TXT/PDF "
                        "variant on EUR-Lex (202/404; official form = OJ PDF)")
                else:
                    meta["content_state"] = "FETCH_FAILED"
                    meta["failure_reason"] = f"eur-lex fetch failed: {reason}"
                rec["meta"] = meta
                out.append(json.dumps(rec, ensure_ascii=False))
                changed = True
                marked += 1
            else:
                out.append(line)
        if changed:
            fp.write_text("\n".join(out) + "\n", encoding="utf-8")
    return marked


def _snapshot(celex: str, text: str, label: str) -> None:
    FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
    if "CELLAR" in label:
        src = f"http://publications.europa.eu/resource/celex/{celex}"
    else:
        src = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
    (FULLTEXT_DIR / f"{celex}.txt").write_text(
        f"# CELEX {celex}\n# {src}\n# 来源 {label}\n"
        f"# 抓取 {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
        f"（正文 {len(text)} 字符）\n\n{text}",
        encoding="utf-8")


def _retry_unfilled() -> list[tuple[str, str]]:
    """CELLAR/站点失败且未满全文的条目（跳过 R(N) 无变体与已达标者）。

    依据记录 meta：failure_reason 含 cellar/eur-lex 失败链且 text<600。
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review")):
            continue
        for line in fp.read_text(encoding="utf-8",
                                 errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = str(rec.get("evidence_id") or "")
            if not eid.startswith("eu_"):
                continue
            celex = eid[len("eu_"):]
            if celex in seen or "R(" in celex:
                continue
            text = str(rec.get("text") or "")
            if len(text) >= 600:
                continue
            meta = rec.get("meta") or {}
            fr = str(meta.get("failure_reason") or "")
            if "no_online_variant" in fr:
                continue
            if "cellar" in fr or "eur-lex" in fr or "unknown" in fr:
                seen.add(celex)
                out.append((celex, "retry"))
    return out


def _contaminated_ids() -> set[str]:
    """扫描已有记录，找需要重抓修正的 evidence_id。

    收录规则（保守）：meta.backfilled_from 为 Formex/PDF —— 这些通道在
    修正前的提取不可靠（可能拿到的是 CELLAR manifest 索引而非正文）；
    重抓时 XHTML 优先，成功则覆盖，失败则保留原内容。
    """
    hits: set[str] = set()
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review")):
            continue
        for line in fp.read_text(encoding="utf-8",
                                 errors="replace").splitlines():
            if not line.strip() or ("CELLAR Formex" not in line
                                    and "CELLAR PDF" not in line):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            meta = rec.get("meta") or {}
            if str(meta.get("backfilled_from") or "") in (
                    "CELLAR Formex", "CELLAR PDF"):
                hits.add(str(rec.get("evidence_id")))
    return hits


async def _run(rounds: int, sleep_s: int, source: str = "auto",
               redo: bool = False, retry_unfilled: bool = False) -> int:
    import httpx
    from app.connectors import get_connector
    targets = _eu_gap_list()
    print(f"EU 在线回填目标：{len(targets)} 条（A2 优先）")
    redo_ids: set[str] = set()
    if redo:
        redo_ids = _contaminated_ids()
        print(f"重抓修正（提取污染）：{len(redo_ids)} 条 {sorted(redo_ids)}")
        targets = [(eid[len("eu_"):] if eid.startswith("eu_") else eid,
                    "redo") for eid in sorted(redo_ids)]
    elif retry_unfilled:
        targets = _retry_unfilled()
        print(f"缺口补抓（非 R(N) 失败者）：{len(targets)} 条")
        for c, _ in targets:
            print(f"   - {c}")
    print(f"通道：{'CELLAR 官方 REST → EUR-Lex 站点回退' if source == 'auto' else source}")
    remaining = [c for c, _ in targets]
    classes = dict(targets)
    ok_bodies: dict[str, tuple[str, bool, str]] = {}
    failures: dict[str, str] = {}
    for rnd in range(1, rounds + 1):
        if not remaining:
            break
        print(f"\n=== Round {rnd}/{rounds}（{len(remaining)} 条）===")

        # ── 通道 1：CELLAR content-negotiation（官方机器接口）──────────
        if source in ("auto", "cellar") and remaining:
            async with httpx.AsyncClient() as client:
                for celex in list(remaining):
                    got = await _fetch_cellar(client, celex)
                    if isinstance(got, tuple):
                        text, label = got
                        short = len(text) < 600
                        ok_bodies[celex] = (text, short, label)
                        _snapshot(celex, text, label)
                        remaining.remove(celex)
                        print(f"  ✅ {celex:<20} [{classes[celex]}] "
                              f"{len(text):>7d} 字符 [{label}]"
                              f"{'（短文书）' if short else ''}")
                    else:
                        failures[celex] = f"cellar:{got}"
                        print(f"  ⚠️ {celex:<20} [{classes[celex]}] CELLAR: {got}")

        # ── 通道 2：EUR-Lex 站点（connector；202 软风控时会被拦截）────
        if source in ("auto", "eurlex") and remaining:
            async with get_connector("eur_lex") as conn:
                for celex in list(remaining):
                    try:
                        text, _ = await conn.fetch_fulltext(celex)
                    except Exception as exc:  # noqa: BLE001
                        prev = failures.get(celex, "")
                        failures[celex] = (
                            f"{prev} | {type(exc).__name__}").strip(" |")
                        print(f"  ❌ {celex:<20} [{classes[celex]}] "
                              f"{type(exc).__name__}")
                        continue
                    if not text or len(text) < 150:
                        prev = failures.get(celex, "")
                        failures[celex] = (
                            f"{prev} | too_short({len(text or '')})").strip(" |")
                        print(f"  ⚠️ {celex:<20} 过短 {len(text or '')}")
                        continue
                    # §4：不得把降级壳/维护页判为全文
                    low = text.lower()
                    if any(m in low for m in DEGRADED_MARKERS):
                        prev = failures.get(celex, "")
                        failures[celex] = (
                            f"{prev} | degraded_shell_content").strip(" |")
                        print(f"  ⚠️ {celex:<20} 降级壳内容，拒绝")
                        continue
                    short = len(text) < 600
                    ok_bodies[celex] = (text, short, "EUR-Lex 在线抓取")
                    _snapshot(celex, text, "EUR-Lex 在线抓取")
                    remaining.remove(celex)
                    print(f"  ✅ {celex:<20} [{classes[celex]}] "
                          f"{len(text):>7d} 字符"
                          f"{'（短文书）' if short else ''}")

    if ok_bodies:
        force = frozenset(
            eid if eid.startswith("eu_") else f"eu_{eid}"
            for eid in redo_ids)
        upd = _merge_bodies(ok_bodies, force)
    else:
        upd = 0
    print(f"\n合并更新 {upd} 条")
    for celex in remaining:
        _mark_failed(celex, failures.get(celex, "unknown"))
    if failures:
        from collections import Counter
        print("失败归类：", dict(Counter(failures.values())))
    return upd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--sleep", type=int, default=20)
    ap.add_argument("--source", default="auto",
                    choices=("auto", "cellar", "eurlex"),
                    help="auto=CELLAR→EUR-Lex；cellar=仅 CELLAR；eurlex=仅站点")
    ap.add_argument("--redo", action="store_true",
                    help="重抓修正被 manifest 污染的条目（强制覆盖）")
    ap.add_argument("--retry-unfilled", action="store_true",
                    help="仅重试 CELLAR/站点失败且未达全文的非 R(N) 条目")
    args = ap.parse_args()
    updated = asyncio.run(_run(args.rounds, args.sleep, args.source,
                               redo=args.redo,
                               retry_unfilled=args.retry_unfilled))
    print(f"→ 完成（更新 {updated}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
