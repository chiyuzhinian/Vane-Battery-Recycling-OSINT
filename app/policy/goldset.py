# -*- coding: utf-8 -*-
"""Gold Set 评估（Phase 4A §9）。

指标：precision / recall / F1 / A1 recall / A2 recall / B recall /
      false_positive_rate / false_negative_rate /
      instrument_type_accuracy / legal_status_accuracy

纪律：数据不足 → 明确 INSUFFICIENT_GOLDSET，不伪造数字。
"""
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import yaml

from app.policy.acceptance import classify_record
from app.policy.legal_identity import resolve_identity

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "outputs"
GOLDSET = ROOT / "sources" / "policy-goldset.yaml"

POSITIVE = {"A1", "A2", "B"}


def _load_records() -> list[dict]:
    rows: dict[str, dict] = {}
    for fp in glob.glob(str(OUT / "*.jsonl")):
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
            if eid and eid not in rows:
                rows[eid] = r
    return list(rows.values())


def _find_record(case: dict, records: list[dict]) -> dict | None:
    m = case.get("must_find") or {}
    # ⚠️ 标题可能含不换行空格（\xa0）（EUR-Lex 标题实测）→ 匹配前归一化空白
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s or "")
    for r in records:
        meta = r.get("meta") or {}
        if "evidence_id" in m and r.get("evidence_id") == m["evidence_id"]:
            return r
        if "celex" in m and meta.get("celex") == m["celex"]:
            return r
        if "document_number" in m and meta.get("document_number") == m["document_number"]:
            return r
        if "nim" in m and str(meta.get("nim_id")) == str(m["nim"]):
            return r
        if "title_contains" in m and norm(m["title_contains"]).lower() in norm(r.get("title")).lower():
            return r
    return None


def evaluate(include_holdout: bool = True) -> dict:
    cases = yaml.safe_load(GOLDSET.read_text(encoding="utf-8"))["cases"]
    if not include_holdout:
        cases = [c for c in cases if not c.get("holdout")]
    records = _load_records()

    tp = fp = fn = tn = 0
    per_class: dict[str, dict] = {"A1": {"tp": 0, "total": 0},
                                  "A2": {"tp": 0, "total": 0},
                                  "B": {"tp": 0, "total": 0}}
    inst_ok = inst_total = 0
    status_ok = status_total = 0
    found_cases = 0
    details: list[dict] = []

    for c in cases:
        r = _find_record(c, records)
        if r is None:
            fn += 1
            details.append({"id": c["id"], "status": "NOT_FOUND"})
            continue
        found_cases += 1
        res = classify_record(r)
        expect = c.get("expected_class")
        got = res.classification
        exp_pos = expect in POSITIVE
        got_pos = got in POSITIVE
        if exp_pos and got_pos:
            tp += 1
            per_class.setdefault(expect, {"tp": 0, "total": 0})
            per_class[expect]["total"] += 1
            if expect == got:
                per_class[expect]["tp"] += 1
        elif exp_pos and not got_pos:
            fn += 1
            per_class.setdefault(expect, {"tp": 0, "total": 0})
            per_class[expect]["total"] += 1
        elif not exp_pos and got_pos:
            fp += 1
        else:
            tn += 1

        # instrument / legal_status 准确率
        e_it = c.get("expected_instrument_type")
        if e_it and e_it != "unknown":
            inst_total += 1
            idn = resolve_identity(r)
            if idn.instrument_type == e_it:
                inst_ok += 1
        e_st = c.get("expected_status")
        if e_st:
            status_total += 1
            idn = resolve_identity(r)
            if idn.status == e_st:
                status_ok += 1

        details.append({"id": c["id"], "status": "OK" if got == expect else "MISMATCH",
                        "expected": expect, "got": got,
                        "conf": round(res.confidence, 2),
                        "holdout": c.get("holdout", False)})

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    insufficient = len(cases) < 20 or found_cases < len(cases) * 0.6

    return {
        "cases_total": len(cases),
        "cases_found": found_cases,
        "INSUFFICIENT_GOLDSET": insufficient,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "a1_recall": round(per_class["A1"]["tp"] / per_class["A1"]["total"], 3)
        if per_class["A1"]["total"] else None,
        "a2_recall": round(per_class["A2"]["tp"] / per_class["A2"]["total"], 3)
        if per_class["A2"]["total"] else None,
        "b_recall": round(per_class["B"]["tp"] / per_class["B"]["total"], 3)
        if per_class["B"]["total"] else None,
        "false_positive_rate": round(fp / (fp + tn), 4) if (fp + tn) else 0.0,
        "false_negative_rate": round(fn / (tp + fn), 4) if (tp + fn) else 0.0,
        "instrument_type_accuracy": round(inst_ok / inst_total, 4) if inst_total else None,
        "legal_status_accuracy": round(status_ok / status_total, 4) if status_total else None,
        "details": details,
    }
