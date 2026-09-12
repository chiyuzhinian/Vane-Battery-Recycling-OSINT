# -*- coding: utf-8 -*-
"""acceptance 冒烟测试：跑用户判例中的真实记录（从库内抽取）。"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402

TARGETS = {
    "eu_32023R1542": "用户✅ 电池法",
    "eu_32025R0606": "用户🟡 回收效率核算（曾✅）",
    "eu_32025R2289": "用户✅ 废电池收集处理规则",
    "eu_32018L0849": "用户✅ ELV+电池修订指令",
    "eu_32026R1738": "用户✅ 车辆循环性法规",
    "eu_52020PC0798": "用户✅ 电池法提案",
    "eu_52025XC00214": "用户✅(按键) 适用指南",
    "eu_32020L0362": "用户🟡 ELV 附件修订",
    "eu_32024R1781": "用户🟡 ESPR",
    "us_fr_2024-09094": "用户✅ 清洁车辆抵免",
    "us_fr_2019-03812": "用户✅ 航空锂电规则",
    "us_fr_2024-08913": "用户❌ FEOC",
}

recs: dict[str, dict] = {}
for fp in glob.glob(str(ROOT / "outputs" / "*.jsonl")):
    if Path(fp).name.startswith(("_", "review")):
        continue
    for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        eid = r.get("evidence_id")
        if eid and eid not in recs:
            recs[eid] = r

print(f"{'记录':22s} {'用户判例':28s} → 分类 / 置信 / 主题")
print("=" * 110)
for eid, note in TARGETS.items():
    r = recs.get(eid)
    if not r:
        print(f"{eid:22s} {note:28s} → ⚠️ 未找到")
        continue
    res = classify_record(r)
    review = " [转人工]" if res.requires_human_review else ""
    print(f"{eid:22s} {note:28s} → {res.classification}{review} "
          f"conf={res.confidence:.2f} topics={res.topic_ids} "
          f"reasons={res.reason_codes}")
    if res.evidence_quotes:
        print(f"      证据: {res.evidence_quotes[0][:100]}")
