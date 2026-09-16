# -*- coding: utf-8 -*-
"""Batch 1C —— 身份补全 overlay（MODE B 早期适配器缺 doc_key/language）。

背景：MODE B 早期轮次（CZ R3 / SK R2 / IT R3）持久化的记录未写
meta.doc_key / meta.language（后续版本已修复）。原始 evidence 不可变
→ 生成 overlay 供验收构建器合并（身份完整度口径以此为输入）。

确定性构造（与新版适配器 doc_key 格式一致）：
  · cz_psp_170_2010     → CZ:SB:170/2010   （cs）
  · sk_slovlex_85_2013  → SK:ZZ:85/2013    （sk）
  · it_normattiva_20g00136 → IT:NIR:code:20G00136（it）
  · it_normattiva_188_2008 → IT:NIR:urn:nir:stato:decreto.legislativo:2008-11-20;188（it，已核实）

用法：py scripts/build_identity_overlay.py
输出：outputs/identity_overlay.jsonl
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_acceptance_table import BATCH1, jid_of, load_records  # noqa

OUT = ROOT / "outputs" / "overlays" / "identity_overlay.jsonl"


def derive(rec: dict) -> dict | None:
    sid = str(rec.get("source_id") or "")
    eid = str(rec.get("evidence_id") or "")
    meta = rec.get("meta") or {}
    if meta.get("doc_key") and meta.get("language"):
        return None
    if sid == "cz_psp":
        m = re.search(r"_(\d{1,4})_(\d{4})$", eid)
        if not m:
            return None
        return {"doc_key": f"CZ:SB:{int(m.group(1))}/{m.group(2)}",
                "language": "cs"}
    if sid == "sk_slovlex":
        m = re.search(r"_(\d{1,4})_(\d{4})$", eid)
        if not m:
            return None
        return {"doc_key": f"SK:ZZ:{int(m.group(1))}/{m.group(2)}",
                "language": "sk"}
    if sid == "it_normattiva":
        m = re.search(r"_(\d{2,3}g\d{4,5})$", eid)
        if m:
            return {"doc_key": f"IT:NIR:code:{m.group(1).upper()}",
                    "language": "it"}
        m = re.search(r"_(\d{3})_(\d{4})$", eid)
        if m:
            return {"doc_key": "IT:NIR:urn:nir:stato:decreto.legislativo:"
                               f"{m.group(2)}-*;{int(m.group(1))}",
                    "language": "it"}
        return None
    return None


def main() -> int:
    records = load_records(ROOT)
    rows = []
    for r in records:
        if jid_of(r) not in BATCH1:
            continue
        d = derive(r)
        if not d:
            continue
        rows.append({"evidence_id": r.get("evidence_id"),
                     "source_id": r.get("source_id"),
                     "jurisdiction": jid_of(r),
                     "identity": d,
                     "method": "deterministic_from_eid"})
    OUT.write_text("\n".join(json.dumps(x, ensure_ascii=False)
                             for x in rows) + "\n", encoding="utf-8")
    print(f"candidates: {len(rows)} → {OUT}")
    for x in rows:
        print(" ", x["evidence_id"], "→", x["identity"]["doc_key"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
