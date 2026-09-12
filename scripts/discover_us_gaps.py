# -*- coding: utf-8 -*-
"""US 侧缺口发现：FR API 扫「边界内高精度短语」（不限机构），与库内对比。

背景
----
EU 侧已用"锚点扫描 → 缺口对比 → 定向补采"闭环补全 34 条。
US 侧做同类检查：只要词表中某些高精度短语（如黑粉、电池处置）
在**未配置的机构**下也有产出，就说明存在缺口。

用法
----
    py scripts/discover_us_gaps.py                 # 扫默认短语
    py scripts/discover_us_gaps.py --since 2018-01-01
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"
API = "https://www.federalregister.gov/api/v1/documents.json"

# 高精度短语（边界核心）——命中多半就是在讲退役电池/黑粉
TERMS = [
    "battery recycling",
    "black mass",
    "lithium-ion battery disposal",
    "spent lithium batteries",
    "electric vehicle battery recycling",
    "battery shredding",
    "end-of-life battery",
    "used electric vehicle batteries",
]


def load_db_doc_numbers() -> set[str]:
    """扫描 outputs 全部 jsonl，收集已入库的 FR document_number。"""
    nums: set[str] = set()
    for fp in sorted(OUT.glob("*.jsonl")):
        if fp.name.startswith("_") or not fp.name.startswith(
                ("eol_", "policy_", "browser_", "us_federal")):
            continue
        for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"document_number"' not in line and "federalregister.gov" not in line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            meta = rec.get("meta") or {}
            num = meta.get("document_number")
            if num:
                nums.add(num)
                continue
            url = rec.get("url") or ""
            if "federalregister.gov/documents/" in url:
                nums.add(url.rstrip("/").rsplit("/", 1)[-1])
            eid = rec.get("evidence_id") or ""
            if eid.startswith("us_fr_"):
                nums.add(eid.replace("us_fr_", ""))
    return nums


async def search(client: httpx.AsyncClient, term: str, since: str) -> list[dict]:
    params = {
        "conditions[term]": term,
        "conditions[publication_date][gte]": since,
        "per_page": 100,
        "order": "newest",
        "fields[]": ["title", "html_url", "publication_date",
                     "document_number", "type", "agencies"],
    }
    # fields[] 需要重复键 → 手工拼 query
    qs = (f"conditions%5Bterm%5D={httpx.QueryParams({'t': term})['t']}"
          f"&conditions%5Bpublication_date%5D%5Bgte%5D={since}"
          f"&per_page=100&order=newest"
          f"&fields%5B%5D=title&fields%5B%5D=html_url&fields%5B%5D=publication_date"
          f"&fields%5B%5D=document_number&fields%5B%5D=type&fields%5B%5D=agencies")
    url = f"{API}?{qs}"
    for attempt in (1, 2):
        try:
            r = await client.get(url, timeout=60)
            if r.status_code == 200:
                return r.json().get("results", [])
            print(f"  ⚠️ 「{term}」HTTP {r.status_code}（第 {attempt} 次）")
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ 「{term}」{type(exc).__name__}（第 {attempt} 次）")
        await asyncio.sleep(2)
    return []


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2018-01-01")
    args = ap.parse_args()

    db_nums = load_db_doc_numbers()
    print(f"库内 FR document_number 索引：{len(db_nums)} 条\n")

    gaps: list[dict] = []
    async with httpx.AsyncClient() as client:
        for term in TERMS:
            results = await search(client, term, args.since)
            missing = [r for r in results
                       if r.get("document_number") not in db_nums]
            print(f"「{term}」→ {len(results)} 条，其中未入库 {len(missing)} 条")
            for r in missing:
                agencies = ", ".join(
                    a.get("raw_name", "") for a in (r.get("agencies") or []))[:60]
                gaps.append({
                    "term": term,
                    "document_number": r.get("document_number"),
                    "title": (r.get("title") or "")[:120],
                    "date": (r.get("publication_date") or "")[:10],
                    "type": r.get("type"),
                    "agencies": agencies,
                    "url": r.get("html_url"),
                })
            await asyncio.sleep(1)   # 礼貌限速（1 req/s）

    print(f"\n=== 未入库候选 {len(gaps)} 条 ===")
    for g in gaps:
        print(f"  · {g['date']} [{g['type']}] {g['title'][:90]}")
        print(f"      {g['agencies']}  {g['document_number']}")
        print(f"      {g['url']}")

    if gaps:
        p = OUT / "_us_gap_candidates.json"
        p.write_text(json.dumps(gaps, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        print(f"\n→ 已写出 {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
