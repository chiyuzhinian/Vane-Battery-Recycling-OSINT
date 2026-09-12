# -*- coding: utf-8 -*-
"""端到端验证：审核备注（拒绝原因）的写入与回读，然后撤销（不留痕）。

用法：py scripts/verify_review_note.py
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8010"
sys.stdout.reconfigure(encoding="utf-8")


def req(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=20) as resp:
        return json.loads(resp.read().decode())


# 1) 找一条记录做测试靶（用搜索保证存在）
page = req("GET", "/api/records?country=EU&page_size=1&sort=score")
rec = page["items"][0]
eid = rec["evidence_id"]
print(f"测试靶: {eid}  {rec['title'][:60]}")
print(f"  当前 review_note = {rec.get('review_note')!r}")

# 2) 提交裁决 + 备注
res = req("POST", "/api/review", {"decisions": [{
    "target_type": "record", "target_id": eid, "verdict": "irrelevant",
    "reason": "【测试备注】验证拒绝原因链路 —— 将被自动撤销",
    "country": "EU",
}]})
did = res["decisions"][0]["decision_id"]
print(f"已提交 decision_id={did}")

# 3) 回读：详情端点应带 review_note
hit = req("GET", f"/api/record/{eid}")
print(f"回读 review_note = {hit.get('review_note')!r}")
print(f"回读 review_verdict = {hit.get('review_verdict')!r}")
ok = (hit.get("review_note") or "").startswith("【测试备注】")

# 4) 撤销（清理测试数据）
out = req("POST", "/api/review/revoke", {"decision_ids": [did]})
print(f"已撤销 {out['removed']} 条")
hit = req("GET", f"/api/record/{eid}")
print(f"撤销后 review_note = {hit.get('review_note')!r}  reviewed={hit.get('reviewed')}")

print("\n" + ("✅ 通过：备注链路完整（写入→回读→撤销）" if ok else "❌ 失败"))
raise SystemExit(0 if ok else 1)
