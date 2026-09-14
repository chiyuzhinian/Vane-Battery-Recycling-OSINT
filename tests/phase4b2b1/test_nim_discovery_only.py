# -*- coding: utf-8 -*-
"""Phase 4B-2B1 §3：NIM 只能是 Discovery Layer（不得 force A1/A2/B）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.acceptance import classify_record  # noqa: E402
from app.policy.domain_scope import guarded_effective_class  # noqa: E402


def _rec(eid="e", sid="eu_nim_cz", title="", text="", meta=None, **kw):
    r = {"evidence_id": eid, "source_id": sid, "title": title, "text": text,
         "meta": meta or {}}
    r.update(kw)
    return r


def test_nim_never_gets_strong_classes():
    cases = [
        _rec(title="Vyhláška o bateriích a akumulátorech",
             meta={"nim_id": "283350"}),
        # 即使标题含 A1 对象词，也封顶 C（不得 force A1）
        _rec(title="Zákon o traction batteries a recyklaci"),
        # 即使正文有主题命中（英文主题词）
        _rec(text="waste batteries recycling efficiency targets " * 40),
        # relevant=True 也不许 force
        _rec(title="Batteriegesetz — waste battery regime",
             relevant=True),
    ]
    for r in cases:
        res = classify_record(r)
        assert res.classification == "C", \
            f"NIM 得到强类 {res.classification}: {r['title']}"
        assert res.relevant is False
        assert "C_DISCOVERY_LAYER_NIM" in res.reason_codes


def test_nim_guarded_effective_class_capped():
    r = _rec(title="Arrêté relatif à l'immatriculation des véhicules")
    assert guarded_effective_class(r, "A2") == "C"
    assert guarded_effective_class(r, "B") == "C"
    assert guarded_effective_class(r, "D") == "D"


def test_non_nim_records_unaffected():
    """对照：非 NIM 的记录不封顶（正常路径）。"""
    r = _rec("n1", sid="us_ecfr",
             title="49 CFR Part 173 — Shippers requirements",
             text="hazardous materials shipments " * 30)
    res = classify_record(r)
    assert "C_DISCOVERY_LAYER_NIM" not in res.reason_codes
