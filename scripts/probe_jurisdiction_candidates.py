# -*- coding: utf-8 -*-
"""probe_jurisdiction_candidates.py —— Step 3 第二轮带重试探测。

对 sources/jurisdiction-priority-signals.yaml::probe_targets 的候选官方入口
做真实 HTTP 探测（**重试 1 次 + 退避 2s**），产物：
    outputs/audit/jurisdiction_pilot_probe_r2.json

分类（供 priority score 使用）：
    http_200 / http_200_spa（200 但疑似 JS shell）/ http_4xx / http_5xx / error

纪律：❌/⚠️ 一律记端点级失败 + 分类，**不得记为"源不可用"**；
     本环境网络限制（超时）与 bot 防护（403/503）分开记录。
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

from app.policy.jurisdiction_priority import load_signals  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "jurisdiction_pilot_probe_r2.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
SPA_MARKERS = re.compile(r"__NEXT_DATA__|ng-app|id=\"app\"|id=\"root\"|vue\.js", re.I)


async def probe_one(client: httpx.AsyncClient, jid: str, url: str,
                    sem: asyncio.Semaphore) -> dict:
    async with sem:
        row = {"id": jid, "url": url, "attempts": 0, "recovered": False}
        for attempt in (1, 2):
            row["attempts"] = attempt
            try:
                r = await client.get(url, headers=UA, timeout=15,
                                     follow_redirects=True)
                text = r.text[:80000]
                row.update(status=r.status_code, bytes=len(r.content),
                           final_url=str(r.url)[:120],
                           spa_suspect=bool(SPA_MARKERS.search(text)) and len(text) < 3500,
                           error="", recovered=(attempt == 2))
                if attempt == 2 and row["recovered"]:
                    row["recovered_from"] = "retry"
                break
            except Exception as exc:  # noqa: BLE001
                row.update(status=None, error=type(exc).__name__, bytes=0,
                           spa_suspect=False)
                if attempt == 1:
                    await asyncio.sleep(2)
        status = row.get("status")
        if status is None:
            row["probe_class"] = "error"
        elif status == 200:
            row["probe_class"] = "http_200_spa" if row.get("spa_suspect") else "http_200"
        elif 400 <= status < 500:
            row["probe_class"] = "http_4xx"
        elif 500 <= status < 600:
            row["probe_class"] = "http_5xx"
        else:
            row["probe_class"] = "unknown"
        return row


async def run() -> int:
    signals = load_signals()
    targets: dict[str, str] = {}
    for group, items in (signals.get("probe_targets") or {}).items():
        for jid, url in items.items():
            targets[jid] = url
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient() as client:
        rows = await asyncio.gather(*[probe_one(client, jid, url, sem)
                                      for jid, url in sorted(targets.items())])
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "note": "第二轮：重试 1 次；分类见 probe_class（priority score 输入）",
               "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for r in rows if r["probe_class"].startswith("http_200"))
    print(f"probe r2: {ok}/{len(rows)} HTTP 200 → {OUT.name}")
    for r in rows:
        flag = {"http_200": "✅", "http_200_spa": "⚠️", "http_4xx": "⛔",
                "http_5xx": "⛔", "error": "❌"}.get(r["probe_class"], "?")
        extra = f" (retry 恢复)" if r.get("recovered") else ""
        print(f"  {flag} {r['id']:8s} {str(r.get('status')):5s} "
              f"{r.get('bytes', 0):>7d}B {r.get('error', '')}{extra}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.parse_args()
    raise SystemExit(asyncio.run(run()))
