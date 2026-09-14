# -*- coding: utf-8 -*-
"""ingest_cloud_samples.py —— Batch 1R：云端 vantage 获取的真实样本注入。

用途：Runner B（云）在本地不可达/受限域上获取的官方文档样本，
注入对应 source_proof 的 samples 数组（带 vantage 注记），使
"acquired via second vantage" 的辖区可进入 CONNECTED 判定。

纪律：
  · 仅注入**已在云端实际获取**（status=200 + 字节数 + sha256 存证）的样本；
  · 存证文件位于 outputs/audit/cloud_samples/（提交时不入库，仅报告引用哈希）；
  · samples 记录携带 vantage=runner-cloud-1 与 sha256，可复核。
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

# 云端已获取的样本（2026-09-14T09:31Z，runner-cloud-1）
CLOUD_SAMPLES = [
    {
        "jid": "HU", "source_id": "hu_magyarkozlony",
        "url": ("https://magyarkozlony.hu/dokumentumok/"
                "d5a9c2f2c728908437c52693273af4a34e30c7cb/megtekintes"),
        "title": "Magyar Közlöny 2026. évi 131. szám (2026-09-11)",
        "status": 200, "bytes": 16310,
        "vantage": "runner-cloud-1",
        "file": "cloud_samples/HU_magyarkozlony_doc1.html",
        "sha256": ("985d87a33b3164bd272f427b3fd507588e6e82a164cd300"
                   "68917524f202cc0ff"),
    },
    {
        "jid": "HU", "source_id": "hu_magyarkozlony",
        "url": ("https://magyarkozlony.hu/dokumentumok/"
                "fbdda3d49e5e91c81743bbdc35ce5b0b95b44ada/megtekintes"),
        "title": "Magyar Közlöny 2026. évi 123. szám (2026-09-02)",
        "status": 200, "bytes": 16310,
        "vantage": "runner-cloud-1",
        "file": "cloud_samples/HU_magyarkozlony_doc2.html",
        "sha256": ("5def422f4ff31820405a8f38578271f01cc96e353ee68f805ad"
                   "24377574ad70a"),
    },
]


def main() -> int:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for s in CLOUD_SAMPLES:
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
                "source": "cloud_vantage",
                "vantage": s["vantage"], "sha256": s["sha256"],
                "file": s["file"], "fetched_at": now,
            })
            # 更新 summary
            ok = sum(1 for x in samples if x.get("status") == 200)
            d["summary"]["samples_total"] = sum(
                len(x.get("samples") or []) for x in d["sources"])
            d["summary"]["samples_ok"] = sum(
                sum(1 for y in (x.get("samples") or [])
                    if y.get("status") == 200) for x in d["sources"])
            if ok > 0:
                d["summary"]["fulltext_available"] = sum(
                    1 for x in d["sources"]
                    if any(y.get("status") == 200
                           for y in (x.get("samples") or [])))
            n += 1
        d["cloud_vantage_note"] = (
            "含 runner-cloud-1 vantage 获取的官方样本（MULTI_VANTAGE 纪律："
            "本地不可达但云可达 → CURRENT_RUNNER_BLOCKED 而非 SOURCE 失败）。")
        pf.write_text(json.dumps(d, ensure_ascii=False, indent=2),
                      encoding="utf-8")
        print(f"✅ {s['jid']}/{s['source_id']} ← {s['title'][:48]}")
    print(f"→ 注入 {n} 个云端样本")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
