# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §2：域/acceptance 语义一致性（contradiction = 0）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.domain_scope import (  # noqa: E402
    FORBIDDEN_BY_SCOPE, guard_class, guarded_effective_class,
    is_domain_acceptance_consistent,
)


def _rec(eid="e", sid="us_ecfr", title="", text="", meta=None, **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_consistency_function_matrix():
    for scope in ("OUT_OF_SCOPE", "GENERAL_BATTERY_BACKGROUND"):
        for cls in ("A1", "A2", "B"):
            assert not is_domain_acceptance_consistent(scope, cls)
        for cls in ("C", "D"):
            assert is_domain_acceptance_consistent(scope, cls)
    for cls in ("A1", "A2"):
        assert not is_domain_acceptance_consistent("SUPPORTING_REGULATION", cls)
    assert is_domain_acceptance_consistent("SUPPORTING_REGULATION", "B")
    # CORE / HORIZONTAL 无禁列
    for cls in ("A1", "A2", "B", "C", "D"):
        assert is_domain_acceptance_consistent("CORE_EV_TRACTION", cls)
        assert is_domain_acceptance_consistent("HORIZONTAL_APPLIES_TO_EV", cls)


def test_guard_output_never_contradicts():
    """护栏输出对所有 scope/class 组合均一致。"""
    for scope in FORBIDDEN_BY_SCOPE:
        for cls in ("A1", "A2", "B", "C", "D"):
            out = guard_class(cls, scope)
            assert is_domain_acceptance_consistent(scope, out), \
                f"{scope}+{cls} -> {out} 矛盾"


def test_real_shaped_records_no_contradiction():
    records = [
        # 排放法规（真无关）→ D
        _rec("r1", title="40 CFR Part 1036 — Control of Emissions",
             text="emission standards for heavy-duty engines " * 30),
        # 危废法规（真支撑）→ SUPPORTING + B
        _rec("r2", title="40 CFR Part 261 — Identification and Listing "
                         "of Hazardous Waste",
             text="hazardous waste management standards " * 30,
             meta={"acceptance_class": "B"}),
        # 危货运输 → SUPPORTING + B（A2 也降 B）
        _rec("r3", title="49 CFR Part 173 — Shippers requirements",
             text="hazardous materials shipments " * 30,
             meta={"acceptance_class": "B"}),
        # 域外（铅酸）→ D
        _rec("r4", title="Lead-acid battery collection program",
             text="lead-acid batteries " * 30,
             meta={"acceptance_class": "B"}),
    ]
    from app.policy.domain_scope import classify_domain_scope
    for r in records:
        scope = classify_domain_scope(r)
        final = guarded_effective_class(
            r, str((r.get("meta") or {}).get("acceptance_class") or "B"))
        assert is_domain_acceptance_consistent(scope, final), \
            f"{r['evidence_id']}: {scope}+{final}"
