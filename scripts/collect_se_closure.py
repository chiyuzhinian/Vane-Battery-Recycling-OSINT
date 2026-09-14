# -*- coding: utf-8 -*-
"""SE closure（2B1 §7）：Transportstyrelsen + SIS 官方样本归档。

MS_TRANSPORT_OR_DANGEROUS_GOODS ← se_transportstyrelsen（Regler 索引 +
farligt gods 搜索页——服务端渲染实证）
MS_STANDARDS_METADATA ← se_sis（标准目录/搜索——metadata-only 口径）
"""
import json
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/126 Safari/537.36"}
SAMPLES = [
    ("se_transportstyrelsen_regler", "se_transportstyrelsen",
     "MS_TRANSPORT_OR_DANGEROUS_GOODS",
     "https://www.transportstyrelsen.se/sv/Regler/",
     "Transportstyrelsen — Regler（瑞典交通法规索引）"),
    ("se_transportstyrelsen_farligt_gods", "se_transportstyrelsen",
     "MS_TRANSPORT_OR_DANGEROUS_GOODS",
     "https://www.transportstyrelsen.se/sv/sok/?q=farligt+gods",
     "Transportstyrelsen — 搜索「farligt gods」（危货法规/表单条目）"),
    ("se_sis_standarder", "se_sis", "MS_STANDARDS_METADATA",
     "https://www.sis.se/sok/?query=battery",
     "SIS — 标准检索「battery」（标准目录 metadata）"),
]


def to_text(html: str) -> str:
    import html as H
    t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    t = re.sub(r"<[^>]+>", " ", t)
    t = H.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def fetch(url: str) -> str | None:
    for i in range(4):
        try:
            r = httpx.get(url, timeout=50, follow_redirects=True, headers=UA)
            if r.status_code == 200 and len(r.content) > 5000:
                return to_text(r.text)
        except Exception as exc:  # noqa: BLE001
            print(f"    retry {i+1}: {type(exc).__name__}")
        time.sleep(4)
    return None


OUT = ROOT / "outputs" / "jurisdiction_SE_20260914.jsonl"
existing = set()
if OUT.exists():
    for line in OUT.read_text(encoding="utf-8").splitlines():
        if line.strip():
            existing.add(json.loads(line)["evidence_id"])

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.domain_scope import classify_domain_scope  # noqa: E402

rows = []
for eid, sid, role, url, label in SAMPLES:
    if eid in existing:
        print(f"已存在 {eid}")
        continue
    text = fetch(url)
    if not text:
        print(f"❌ {eid}: 抓取失败")
        continue
    rec = {
        "evidence_id": eid, "channel": "connector", "source_id": sid,
        "region": "SE", "url": url, "title": label, "publish_date": "",
        "meta": {"region": "SE", "jurisdiction": "SE",
                 "collector": "se_closure_2b1", "content_state": "FULLTEXT",
                 "source_role": role, "language": "sv",
                 "official_domain": url.split("/")[2]},
        "text": text[:400000],
    }
    res = classify_record(rec)
    rec["relevant"] = res.classification in ("A1", "A2", "B")
    rec["relevance_score"] = 0.0
    rec["meta"]["acceptance_class"] = res.classification
    scope = classify_domain_scope(rec)
    print(f"  + {eid}: {len(text)}c class={res.classification} scope={scope}")
    rows.append(rec)

if rows:
    with OUT.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n→ 追加 {len(rows)} 条至 {OUT.name}")
else:
    print("\n无新增")
