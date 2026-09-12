# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 7：官方家族关系回归。

纪律：家族关系必须来自官方数据；查询执行且为空 → absent_official（官方缺席≠缺口）。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.family_official import merge_family, normalize_rows  # noqa: E402
from app.policy.legal_graph import load_official_relations  # noqa: E402


def test_normalize_rows_dedupe_and_sort():
    rows = [
        {"src": {"value": "u1"}, "celex": {"value": "32008L0103"},
         "date": {"value": "2008-11-19T00:00:00"}},
        {"src": {"value": "u2"}, "celex": {"value": "32008L0103"},
         "date": {"value": "2008-11-19T00:00:00"}},   # 重复
        {"src": {"value": "u3"}, "celex": {"value": "32013L0056"},
         "date": {"value": "2013-12-10T00:00:00"}},
    ]
    out = normalize_rows(rows)
    assert [r["celex"] for r in out] == ["32008L0103", "32013L0056"]
    assert out[0]["date"] == "2008-11-19"


def test_merge_resolves_elv_style_gap():
    """ELV：语料只有 TRANSPOSES，AMENDS/CORRIGENDUM_OF 由官方关系解决。"""
    official = {
        "AMENDS": [{"celex": "32005D0063", "date": "2005-01-24", "uri": "u"}],
        "CORRIGENDUM_OF": [{"celex": "32000L0053R(01)", "date": "2015-04-11", "uri": "u"}],
        "TRANSPOSES": [{"celex": "71975L0442HUN_24504", "date": "", "uri": "u"}],
    }
    merge = merge_family(expected=["TRANSPOSES", "AMENDS", "CORRIGENDUM_OF"],
                         corpus_found={"TRANSPOSES"}, official=official)
    assert merge["unresolved"] == []
    assert set(merge["resolved_official"]) == {"AMENDS", "CORRIGENDUM_OF"}
    assert merge["completeness"] == 1.0


def test_merge_marks_absent_official():
    """官方查询执行且为空 → absent_official（不得算作缺口）。"""
    official = {"AMENDS": [], "REPEALS": [{"celex": "32023R1542", "date": "", "uri": "u"}]}
    merge = merge_family(expected=["AMENDS", "REPEALS"], corpus_found=set(),
                         official=official)
    assert merge["resolved_official"] == ["REPEALS"]
    assert "AMENDS" in merge["unresolved"]
    assert merge["absent_official"] == ["AMENDS"]


def test_merge_without_official_keeps_unresolved():
    merge = merge_family(expected=["AMENDS", "REPEALS"], corpus_found=set(),
                         official=None)
    assert merge["unresolved"] == ["AMENDS", "REPEALS"]
    assert merge["absent_official"] == []


def test_load_official_relations_unwraps_file():
    payload = {
        "roots": {
            "32000L0053": {
                "work": "http://example/work",
                "relations": {"AMENDS": [{"celex": "32005D0063"}]},
            }
        }
    }
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as td:
        fp = Path(td) / "off.json"
        fp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        data = load_official_relations(fp)
        assert data["32000L0053"]["AMENDS"][0]["celex"] == "32005D0063"
