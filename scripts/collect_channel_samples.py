# -*- coding: utf-8 -*-
"""2B1 §8：GA（EPD）+ EE（Keskkonnaamet/气候部）通道适配样本采集。

adapted 判定 = 官方通道 + 真实样本 + 可重复采集（本脚本即重复采集器）。
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
    # US-GA — EPD（官方环保署；立法站 SPA/401 仍阻）
    ("us_ga_epd_land_protection", "us_ga_epd", "US-GA",
     "https://epd.georgia.gov/about-us/land-protection-branch",
     "GA EPD — Land Protection Branch（固废/危废主管分支）"),
    ("us_ga_epd_hazardous_waste", "us_ga_epd", "US-GA",
     "https://epd.georgia.gov/about-us/land-protection-branch/hazardous-waste",
     "GA EPD — Hazardous Waste（危废管理）"),
    # EE — Keskkonnaamet + 气候部（RT SPA 壳仍阻）
    ("ee_keskkonnaamet_home", "ee_keskkonnaamet", "EE",
     "https://keskkonnaamet.ee/",
     "Keskkonnaamet（爱沙尼亚环境署）— 主页"),
    ("ee_kliimaministeerium_home", "ee_kliimaministeerium", "EE",
     "https://kliimaministeerium.ee/",
     "Kliimaministeerium（爱沙尼亚气候部）— 主页"),
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
            if r.status_code == 200 and len(r.content) > 8000:
                return to_text(r.text)
        except Exception as exc:  # noqa: BLE001
            print(f"    retry {i+1}: {type(exc).__name__}")
        time.sleep(4)
    return None


from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.domain_scope import classify_domain_scope  # noqa: E402

OUTS = {jid: ROOT / "outputs" / f"jurisdiction_{jid}_20260914.jsonl"
        for jid in ("US-GA", "EE")}
existing = set()
for fp in OUTS.values():
    if fp.exists():
        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(json.loads(line)["evidence_id"])

rows: dict[str, list] = {"US-GA": [], "EE": []}
for eid, sid, jid, url, label in SAMPLES:
    if eid in existing:
        print(f"已存在 {eid}")
        continue
    text = fetch(url)
    if not text:
        print(f"❌ {eid}: 抓取失败")
        continue
    rec = {
        "evidence_id": eid, "channel": "connector", "source_id": sid,
        "region": jid, "url": url, "title": label, "publish_date": "",
        "meta": {"region": jid, "jurisdiction": jid,
                 "collector": "channel_adapt_2b1",
                 "content_state": "FULLTEXT",
                 "source_role": "STATE_ENVIRONMENT_AGENCY" if jid == "US-GA"
                 else "MS_ENVIRONMENT_MINISTRY_OR_AGENCY",
                 "official_domain": url.split("/")[2],
                 "identity_status": "NOT_APPLICABLE_PAGE: agency homepage "
                                    "(no document identifier concept)"},
        "text": text[:400000],
    }
    res = classify_record(rec)
    rec["relevant"] = res.classification in ("A1", "A2", "B")
    rec["relevance_score"] = 0.0
    rec["meta"]["acceptance_class"] = res.classification
    print(f"  + {eid}: {len(text)}c class={res.classification} "
          f"scope={classify_domain_scope(rec)}")
    rows[jid].append(rec)

for jid, recs in rows.items():
    if not recs:
        continue
    with OUTS[jid].open("a", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"→ {jid}: 追加 {len(recs)} 条")
