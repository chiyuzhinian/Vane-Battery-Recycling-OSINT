# -*- coding: utf-8 -*-
"""onboard_jurisdiction_sources.py —— Step 4：Source Proof 执行器。

对 sources/jurisdiction-sources/{JID}.yaml 声明的候选源：
    1) probe 入口页（真实 HTTP）
    2) 执行检索尝试（search_attempts）→ 解析文书链接（link_include/link_keywords）
    3) 抓取 3–10 条真实样本（检索提取优先 + samples_known 补充）
    4) 生成 outputs/audit/source_proofs/{JID}.json（能力矩阵 + known_limitations）

用法：
    py scripts/onboard_jurisdiction_sources.py --jurisdictions SE,PL,BE,FI,EE
    py scripts/onboard_jurisdiction_sources.py --all
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.source_proof import (  # noqa: E402
    JurisdictionSources, SampleEvidence, SearchEvidence, SourceProof,
    build_limitations, derive_capabilities, now_utc, write_proof,
)

SOURCES_DIR = ROOT / "sources" / "jurisdiction-sources"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
HREF_RE = re.compile(r'href="([^"]+)"', re.I)
MAX_SAMPLES = 5


def load_sources_file(jid: str) -> JurisdictionSources:
    fp = SOURCES_DIR / f"{jid}.yaml"
    if not fp.exists():
        raise SystemExit(f"❌ 缺失源配置文件：{fp}")
    return JurisdictionSources(**yaml.safe_load(fp.read_text(encoding="utf-8")))


def _abs(base: str, link: str) -> str:
    if link.startswith("http"):
        return link
    if link.startswith("/"):
        m = re.match(r"(https?://[^/]+)", base)
        return (m.group(1) if m else "") + link
    return base.rstrip("/") + "/" + link


def extract_doc_links(html: str, base_url: str,
                      cfg: JurisdictionSources) -> tuple[list[str], bool]:
    """→ (链接列表, 是否经关键词上下文核验)。

    关键词过滤命中 → (filtered, True)；否则回退全量 (out, False)
    （回退仅为样本抓取便利；**不得用于声称检索能力**）。
    """
    kw = re.compile(cfg.link_keywords, re.I)
    out: list[str] = []
    for m in HREF_RE.finditer(html):
        link = m.group(1)
        if any(pat in link for pat in cfg.link_include):
            absu = _abs(base_url, link)
            if absu not in out:
                out.append(absu)
    if kw:
        filtered: list[str] = []
        for m in HREF_RE.finditer(html):
            link = m.group(1)
            if not any(pat in link for pat in cfg.link_include):
                continue
            ctx = html[max(0, m.start() - 80):m.end() + 120]
            if kw.search(ctx):
                absu = _abs(base_url, link)
                if absu not in filtered:
                    filtered.append(absu)
        if filtered:
            return filtered, True
    return out, False


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[httpx.Response | None, str]:
    """GET + 瞬态重试 1 次（退避 2s）。"""
    try:
        r = await client.get(url, headers=UA, timeout=25, follow_redirects=True)
        return r, ""
    except Exception as exc:  # noqa: BLE001
        await asyncio.sleep(2)
        try:
            r = await client.get(url, headers=UA, timeout=25, follow_redirects=True)
            return r, ""
        except Exception as exc2:  # noqa: BLE001
            return None, type(exc2).__name__


def title_of(html: str) -> str:
    m = TITLE_RE.search(html)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:160] if m else ""


async def build_source_proof(client: httpx.AsyncClient,
                             cfg: JurisdictionSources, sc) -> SourceProof:
    proof = SourceProof(source_role=sc.source_role, source_id=sc.source_id,
                        official_owner=sc.official_owner,
                        official_domain=sc.official_domain,
                        access_method=sc.access_method,
                        language=cfg.language, entry_url=sc.entry_url,
                        verified_at=now_utc())
    entry_links = 0
    if sc.entry_url:
        r, err = await fetch(client, sc.entry_url)
        if r is not None:
            proof.probe = {"status": r.status_code, "bytes": len(r.content),
                           "content_type": r.headers.get("content-type", "")[:60],
                           "title": title_of(r.text)}
            links, _matched = extract_doc_links(r.text, str(r.url), cfg)
            entry_links = len(links)
            proof.probe["doc_links"] = entry_links
        else:
            proof.probe = {"error": err}
    extracted: list[str] = []
    for url in sc.search_attempts:
        r, err = await fetch(client, url)
        if r is None:
            proof.searches.append(SearchEvidence(url=url, error=err))
            continue
        links, matched = extract_doc_links(r.text, str(r.url), cfg)
        proof.searches.append(SearchEvidence(
            url=url, status=r.status_code, bytes=len(r.content),
            links_extracted=len(links), keyword_matched=matched,
            sample_links=links[:3]))
        if matched:
            extracted += links
    # 样本：检索提取优先 → samples_known 补充 → 去重
    picked: list[tuple[str, str]] = [(u, "extracted") for u in extracted[:3]]
    for u in sc.samples_known:
        if len(picked) >= MAX_SAMPLES:
            break
        if u not in [p[0] for p in picked]:
            picked.append((u, "known"))
    seen: set[str] = set()
    for url, origin in picked:
        if url in seen:
            continue
        seen.add(url)
        r, err = await fetch(client, url)
        if r is None:
            proof.samples.append(SampleEvidence(url=url, error=err, source=origin))
            continue
        proof.samples.append(SampleEvidence(
            url=str(r.url)[:200], title=title_of(r.text),
            status=r.status_code, bytes=len(r.content), source=origin))
    proof.capabilities = derive_capabilities(proof.searches, proof.samples,
                                             entry_links=entry_links)
    proof.known_limitations = build_limitations(proof.searches, proof.samples,
                                                entry_links=entry_links)
    if sc.note:
        proof.known_limitations.append(f"note: {sc.note}")
    return proof


async def run_for(jid: str) -> int:
    cfg = load_sources_file(jid)
    async with httpx.AsyncClient() as client:
        proofs = []
        for sc in cfg.sources:
            p = await build_source_proof(client, cfg, sc)
            proofs.append(p)
            c = p.capabilities
            print(f"  [{jid}] {sc.source_id:22s} search={int(c['search_available'])} "
                  f"enum={int(c['enumeration_available'])} "
                  f"meta={int(c['metadata_available'])} "
                  f"fulltext={int(c['fulltext_available'])} "
                  f"samples_ok={sum(1 for s in p.samples if s.status == 200)}"
                  f"/{len(p.samples)}")
            for lim in p.known_limitations[:3]:
                print(f"        ⚠ {lim}")
    fp = write_proof(jid, proofs)
    s = __import__("json").loads(fp.read_text(encoding="utf-8"))["summary"]
    print(f"  → {jid}: {s['sources']} 源 ｜ 可检索 {s['search_available']} ｜ "
          f"全文 {s['fulltext_available']} ｜ 样本 {s['samples_ok']}/{s['samples_total']}")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jurisdictions", default="")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    if args.all:
        jids = sorted(p.stem for p in SOURCES_DIR.glob("*.yaml"))
    else:
        jids = [j for j in args.jurisdictions.split(",") if j]
    if not jids:
        raise SystemExit("用法：--jurisdictions SE,PL 或 --all")
    print(f"=== Source Proof：{', '.join(jids)} ===")
    for jid in jids:
        await run_for(jid)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
