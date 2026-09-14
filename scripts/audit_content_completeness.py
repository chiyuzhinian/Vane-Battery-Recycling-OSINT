# -*- coding: utf-8 -*-
"""audit_content_completeness.py —— Phase 4B-2B1 §4/§5。

产物：outputs/audit/content_completeness.json
字段：evidence_id, jurisdiction, acceptance_class, content_state,
      text_length, official_source, fulltext_available,
      clause_evidence_available, backfill_status, failure_reason
汇总：A1/A2/B 全文率、B clause 率、backfill 优先队列（P0 A1→A2→B、
      P1 pilot C、P2 其余）。

用法：py scripts/audit_content_completeness.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.backfill import load_records  # noqa: E402
from app.policy.content_state import (  # noqa: E402
    classify_content_state, has_clause_evidence)
from app.policy.domain_scope import guarded_effective_class  # noqa: E402
from app.policy.jurisdiction_map import jurisdiction_of  # noqa: E402

OUT = ROOT / "outputs" / "audit" / "content_completeness.json"

PILOT_JIDS = ("SE", "FI", "US-CA", "US-WA")


def _official(record: dict) -> bool:
    meta = record.get("meta") or {}
    if meta.get("official_domain"):
        return True
    sid = str(record.get("source_id") or "")
    return sid.startswith(("us_", "eu_", "se_", "fi_", "fr_", "nl_", "de_",
                           "es_", "pl_", "ky_", "cbp_", "int_", "browser_"))


def _priority(cls: str, jid: str) -> str:
    """§5 回填优先级：P0=A1/A2/B ｜ P1=pilot C ｜ P2=其余 C。"""
    if cls in ("A1", "A2", "B"):
        return "P0"
    if jid in PILOT_JIDS:
        return "P1"
    return "P2"


def main() -> int:
    recs = load_records(ROOT)
    rows: list[dict] = []
    nim_rows = 0
    for r in recs:
        sid = str(r.get("source_id") or "")
        try:
            raw = classify_record(r).classification
        except Exception:  # noqa: BLE001
            continue
        cls = guarded_effective_class(r, raw)
        if sid.startswith("eu_nim_"):
            nim_rows += 1
            cls = "C"
        state = classify_content_state(r)
        text_len = len(r.get("text") or "")
        clause = has_clause_evidence(r) if cls == "B" else False
        backfill = "none"
        reason = ""
        if state in ("NOT_APPLICABLE", "PAYWALLED_KNOWN"):
            pass  # 非文书/付费墙：不要求全文
        elif cls in ("A1", "A2", "B") and state != "FULLTEXT":
            backfill = _priority(cls, jurisdiction_of(r))
            reason = state
        elif cls == "C" and state == "PLACEHOLDER":
            backfill = _priority(cls, jurisdiction_of(r))
            reason = "placeholder"
        elif state == "FETCH_FAILED":
            backfill = "P0"
            reason = "fetch_failed"
        rows.append({
            "evidence_id": r.get("evidence_id"),
            "jurisdiction": jurisdiction_of(r),
            "acceptance_class": cls,
            "content_state": state,
            "text_length": text_len,
            "official_source": _official(r),
            "fulltext_available": state == "FULLTEXT",
            "clause_evidence_available": clause,
            "backfill_status": backfill,
            "failure_reason": reason,
            "b_status": ("confirmed" if clause else "candidate")
            if cls == "B" else "",
        })

    summary: dict = {"total": len(rows), "nim_excluded": nim_rows}
    # 非文书（NOT_APPLICABLE：企业数据线）、付费墙（PAYWALLED_KNOWN）
    # 不适用全文要求（2B1 口径；与规格 §4 “不要求 C/D 全文”同理）
    applicable = [x for x in rows
                  if x["content_state"] not in ("NOT_APPLICABLE",
                                                "PAYWALLED_KNOWN")]
    summary["applicable"] = len(applicable)
    for want in ("A1", "A2", "B"):
        sub = [x for x in applicable if x["acceptance_class"] == want]
        full = [x for x in sub if x["fulltext_available"]]
        clause = [x for x in sub if x["clause_evidence_available"]]
        summary[want] = {
            "total": len(sub), "fulltext": len(full),
            "fulltext_pct": round(len(full) / max(len(sub), 1) * 100, 1),
            "clause_evidence": len(clause),
            "clause_pct": round(len(clause) / max(len(sub), 1) * 100, 1),
        }
    states: dict[str, int] = {}
    for x in rows:
        states[x["content_state"]] = states.get(x["content_state"], 0) + 1
    summary["content_states"] = states
    summary["b_candidates"] = sum(1 for x in rows if x["b_status"] == "candidate")
    queue = [x for x in rows if x["backfill_status"].startswith("P")]
    queue.sort(key=lambda x: (x["backfill_status"], x["evidence_id"]))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": ("content_state 只读判定；HTTP 403 != PAYWALLED_KNOWN；"
                 "B_CANDIDATE = 无条款证据（不得作 confirmed B）。"),
        "summary": summary,
        "backfill_queue": queue,
        "records": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"records={len(rows)} (nim={nim_rows})")
    for want in ("A1", "A2", "B"):
        s = summary[want]
        print(f"  {want}: fulltext {s['fulltext']}/{s['total']} "
              f"({s['fulltext_pct']}%) | clause {s['clause_evidence']} "
              f"({s['clause_pct']}%)")
    print("  states:", states)
    print(f"  b_candidates={summary['b_candidates']}  "
          f"backfill_queue={len(queue)}")
    p0 = sum(1 for x in queue if x["backfill_status"] == "P0")
    p1 = sum(1 for x in queue if x["backfill_status"] == "P1")
    p2 = sum(1 for x in queue if x["backfill_status"] == "P2")
    print(f"  backfill: P0={p0} P1={p1} P2={p2}")
    print(f"→ 已写 {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
