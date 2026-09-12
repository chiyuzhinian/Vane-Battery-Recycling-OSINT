# -*- coding: utf-8 -*-
"""discover_a1_candidates.py —— Phase 4B-1 Step 9：A1（EV 电池/黑粉专项）候选发现。

三条路线（规格 §10）：
    A 官方枚举     ：EUR-Lex CELEX 年份+标题关键词（SPARQL）+ FR 机构枚举
    B 母语全文检索 ：FR 引号短语（"electric vehicle battery" / "black mass"）
    C 关系扩张     ：官方家族产物中的成员（按 CELEX 年段 + 标题关键词过滤）

产物：outputs/audit/a1_candidates.json
用法：py scripts/discover_a1_candidates.py [--json]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.connectors.eur_lex import CDM, EurLexConnector  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "a1_candidates.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

#: A1 对象锚点（EV 牵引电池 / 黑粉），多语言
A1_PATTERNS = re.compile(
    r"electric[\s-]vehicl\w*\s+batter|traction\s+batter|batter\w*\s+of\s+electric"
    r"|end-of-life\s+electric|black\s+mass|masse\s+noire|schwarzmasse"
    r"|batterie\s+de\s+traction|bateria\s+de\s+tracci[oó]n|tractiebatterij",
    re.I)

#: 排除锚点（消费/便携/汽车整车，而非牵引电池专项）
EXCLUDE_PATTERNS = re.compile(
    r"portable\s+batter|household\s+batter|consumer\s+batter|button\s+cell"
    r"|motor\s+vehicles?\s+emission|fuel\s+economy|tyres?|seat\s+belts?", re.I)

Q_EU_TITLE = ""   # （废弃：全表标题正则在 Virtuoso 上超时；改用已验证的关键词通道）


def screen(title: str) -> tuple[bool, str]:
    t = title or ""
    if not A1_PATTERNS.search(t):
        return False, "no_a1_anchor"
    if EXCLUDE_PATTERNS.search(t):
        return False, "excluded_scope(portable/vehicle-adjacent)"
    return True, "A1_candidate"


async def eu_title_search() -> list[dict]:
    """EUR-Lex 关键词通道（已验证可用）：_fetch_by_keyword → 标题筛选。"""
    conn = EurLexConnector()
    out: list[dict] = []
    seen: set[str] = set()
    for kw in ("electric vehicle batter", "traction batter", "black mass"):
        try:
            evidences = await conn._fetch_by_keyword(kw, since="2019-01-01",
                                                     limit=60)
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ EUR-Lex 关键词检索（{kw}）失败：{type(exc).__name__}")
            continue
        for ev in evidences:
            eid = ev.evidence_id
            if eid in seen:
                continue
            seen.add(eid)
            title = ev.source_title or ""
            ok, reason = screen(title)
            out.append({"route": "B_eurlex_keyword", "id": eid, "title": title,
                        "date": ev.publish_date.date().isoformat()
                        if ev.publish_date else "",
                        "url": ev.source_url,
                        "a1_screen": reason, "a1_candidate": ok})
    return out


async def fr_phrase_search(terms: list[str]) -> list[dict]:
    out: list[dict] = []
    async with httpx.AsyncClient(headers=UA, timeout=40) as client:
        for term in terms:
            try:
                r = await client.get(
                    "https://www.federalregister.gov/api/v1/documents.json",
                    params={"conditions[term]": f'"{term}"', "per_page": "20",
                            "order": "newest",
                            "fields[]": ["title", "document_number", "type",
                                         "publication_date", "html_url"]})
                payload = r.json()
            except Exception as exc:  # noqa: BLE001
                print(f"  ⚠️ FR 检索（{term}）失败：{type(exc).__name__}")
                continue
            for doc in payload.get("results", []):
                title = doc.get("title") or ""
                ok, reason = screen(title)
                out.append({"route": "B_fr_phrase", "id": doc.get("document_number"),
                            "title": title, "fr_type": doc.get("type"),
                            "date": doc.get("publication_date"),
                            "url": doc.get("html_url"),
                            "a1_screen": reason, "a1_candidate": ok})
    return out


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    print("· 路线 A/B：EUR-Lex 标题检索（EV 电池/黑粉，多语言锚点）")
    eu = await eu_title_search()
    print(f"  → {len(eu)} 条候选（A1 命中 {sum(1 for x in eu if x['a1_candidate'])}）")
    print("· 路线 B：FR 引号短语检索")
    fr = await fr_phrase_search(["electric vehicle battery", "traction battery",
                                 "black mass"])
    print(f"  → {len(fr)} 条候选（A1 命中 {sum(1 for x in fr if x['a1_candidate'])}）")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "a1_total": sum(1 for x in (eu + fr) if x["a1_candidate"]),
        "candidates": eu + fr,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("\n=== A1 候选（通过筛选）===")
    for x in payload["candidates"]:
        if x["a1_candidate"]:
            print(f"  ✅ [{x['route']}] {x['id']} ｜ {x['title'][:100]}")
    print("\n=== 被排除样例（前 10）===")
    for x in [c for c in payload["candidates"] if not c["a1_candidate"]][:10]:
        print(f"  ✗ [{x['a1_screen']}] {x['title'][:90]}")
    print(f"\n→ 已写 {OUT.name}（候选 {len(payload['candidates'])}，A1 {payload['a1_total']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
