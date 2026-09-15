# -*- coding: utf-8 -*-
"""ingest_browser_samples.py —— Batch 1R-2：浏览器通道（真实浏览器栈）样本注入。

用途：脚本通道被 bot 壳 403、但真实浏览器栈（MCP Playwright / WebView2）
可达的官方页面，以 desktop-browser 通道获取，注入 source_proof
（带 vantage + sha256 + 本地存证文件），使辖区进入 CONNECTED 判定。

纪律：
  · 仅注入**浏览器通道实际获取**（HTTP 200 + 字节数 + sha256）的样本；
  · 存证文件位于 outputs/audit/browser_samples/（提交不入库，报告引用哈希）；
  · samples 记录携带 vantage=desktop-browser-mcp 与 sha256，可复核。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

PROOFS = ROOT / "outputs" / "audit" / "source_proofs"

# 浏览器通道（MCP Playwright，真实浏览器栈）已获取的样本（2026-09-15）
BROWSER_SAMPLES = [
    {
        "jid": "US-MI", "source_id": "us_mi_egle",
        "url": ("https://www.michigan.gov/egle/about/organization/"
                "materials-management"),
        "title": "Materials Management Division（Michigan EGLE）",
        "status": 200, "bytes": 409386,
        "vantage": "desktop-browser-mcp",
        "file": "browser_samples/US-MI_egle_materials-management.html",
        "sha256": ("dc61878457849a2e1375b9450b750d6813d317a965c0e179"
                   "d1a25b52a5e03eba"),
    },
    {
        "jid": "US-MI", "source_id": "us_mi_egle",
        "url": ("https://www.michigan.gov/egle/about/organization/"
                "materials-management/recycling"),
        "title": "Recycling（Michigan EGLE）",
        "status": 200, "bytes": 479683,
        "vantage": "desktop-browser-mcp",
        "file": "browser_samples/US-MI_egle_recycling.html",
        "sha256": ("fe338c78bcb9ba9935f056c50677cdcd495bc92216e93391"
                   "1ff6e443844d64d1"),
    },
]

LIMITATION_NOTES = {
    "us_mi_egle": (
        "browser 通道（desktop-browser-mcp 真实浏览器栈）实测 200 ✓："
        "脚本端 403 为 bot 壳；执行路线=browser channel；2 样本 sha256 存证。"),
    "us_mi_legislature": (
        "browser 通道复测（2026-09-15）：HTTP 403 Forbidden（真实浏览器同判）"
        "——多通道一致拒绝，如实保留 BLOCKED。"),
}


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    touched: set[str] = set()
    for s in BROWSER_SAMPLES:
        pf = PROOFS / f"{s['jid']}.json"
        if not pf.exists():
            print(f"⚠ {s['jid']}: 缺 proof")
            continue
        d = json.loads(pf.read_text(encoding="utf-8"))
        for src in d["sources"]:
            if src.get("source_id") != s["source_id"]:
                continue
            samples = src.setdefault("samples", [])
            if any(x.get("url") == s["url"] for x in samples):
                continue
            samples.append({
                "url": s["url"], "title": s["title"],
                "status": s["status"], "bytes": s["bytes"],
                "source": "browser_vantage",
                "vantage": s["vantage"], "sha256": s["sha256"],
                "file": s["file"], "fetched_at": now,
            })
            n += 1
        for src in d["sources"]:
            note = LIMITATION_NOTES.get(src.get("source_id"))
            if note:
                lim = src.setdefault("known_limitations", [])
                if note not in lim:
                    lim.append(note)
        d["summary"]["samples_total"] = sum(
            len(x.get("samples") or []) for x in d["sources"])
        d["summary"]["samples_ok"] = sum(
            sum(1 for y in (x.get("samples") or []) if y.get("status") == 200)
            for x in d["sources"])
        d["summary"]["fulltext_available"] = sum(
            1 for x in d["sources"]
            if any(y.get("status") == 200 for y in (x.get("samples") or [])))
        d["browser_vantage_note"] = (
            "含 desktop-browser-mcp（真实浏览器栈）vantage 获取的官方样本；"
            "脚本端 403（bot 壳）→ 执行路线=browser channel（MULTI_CHANNEL 纪律）。")
        pf.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        touched.add(s["jid"])
        print(f"✅ {s['jid']}/{s['source_id']} ← {s['title'][:46]}")
    print(f"→ 注入 {n} 个浏览器样本（{', '.join(sorted(touched))}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
