# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 2：backfill 过滤/合并/度量回归。

纪律：
    · 默认 dry-run（本文件验证 write_overlay 只在显式调用时落盘）
    · overlay 为增量合并（保留旧行）
    · FR 身份合并后 canonical_id / official_identifier 必须来自 FR 官方字段
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.backfill import (  # noqa: E402
    build_overlay_row, filter_records, load_jsonl, merge_rows_into_overlay,
    record_completeness, region_of, role_source_ids, write_overlay,
)


def _rec(eid: str, sid: str = "us_federal_register", title: str = "Notice of x",
         meta: dict | None = None, region: str = "") -> dict:
    return {"evidence_id": eid, "source_id": sid, "title": title,
            "meta": meta or {}, "text": "", "url": "https://example.gov/x",
            "region": region, "relevant": True}


FR_IDENTITY = {
    "canonical_id": "FR:2019-03812",
    "official_identifier": "84 FR 8006",
    "issuer": "Transportation Department",
    "instrument_type": "administrative_rule",
    "binding_force": "binding",
    "legal_status": "effective",
    "fr_rin": ["2137-AF20"],
    "cfr_references": [{"title": 49, "part": "172", "chapter": None}],
}


# ------------------------------------------------------------ region / role

def test_region_classification():
    assert region_of(_rec("a")) == "US"
    assert region_of(_rec("b", sid="eu_nim_cz")) == "EU"
    assert region_of(_rec("c", sid="cninfo")) == "OTHER"
    assert region_of({"evidence_id": "d", "region": "EU"}) == "EU"
    # 浏览器通道
    assert region_of(_rec("e", sid="browser_calrecycle")) == "US"


def test_role_filter_expands_aliases():
    from app.policy.config import load_aliases
    alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
    known = ["eu_nim_cz", "eu_nim_be", "eur_lex", "eu_eurlex_battery_reg"]
    ids = role_source_ids("EURLEX_NIM", alias_map, known)
    assert ids == ["eu_nim_cz", "eu_nim_be"]
    records = [_rec("1", sid="eu_nim_cz"), _rec("2", sid="us_federal_register")]
    out = filter_records(records, source_role="EURLEX_NIM",
                         alias_map=alias_map, known_source_ids=known)
    assert [r["evidence_id"] for r in out] == ["1"]


def test_unknown_role_fails_fast():
    try:
        role_source_ids("NOT_A_ROLE", {}, [])
    except ValueError as e:
        assert "NOT_A_ROLE" in str(e)
    else:  # pragma: no cover
        raise AssertionError("未知角色必须 fail-fast")


def test_region_and_limit_filters():
    records = [_rec(f"us-{i}") for i in range(5)] + \
              [_rec(f"eu-{i}", sid="eu_nim_cz") for i in range(3)]
    us = filter_records(records, region="US")
    assert len(us) == 5
    limited = filter_records(records, region="US", limit=2)
    assert len(limited) == 2


# ------------------------------------------------------------ only-missing

def test_only_missing_uses_identity_completeness():
    incomplete = _rec("us_fr_1")                       # instrument/status 缺失
    complete = {
        "evidence_id": "eu_x", "source_id": "eur_lex",
        "title": "Regulation (EU) 2023/1542 concerning batteries and waste batteries",
        "meta": {"celex": "32023R1542", "in_force": "1"},
        "text": "", "url": "https://eur-lex.europa.eu/x", "relevant": True,
    }
    out = filter_records([incomplete, complete], only_missing=True)
    assert [r["evidence_id"] for r in out] == ["us_fr_1"]


# ------------------------------------------------------------ overlay 行

def test_overlay_row_merges_fr_identity():
    row = build_overlay_row(_rec("us_fr_2019-03812"), fr_identity=FR_IDENTITY)
    assert row["legal_identity"]["canonical_id"] == "FR:2019-03812"
    assert row["legal_identity"]["official_identifier"] == "84 FR 8006"
    assert row["legal_identity"]["issuer"] == "Transportation Department"
    assert row["instrument_type"] == "administrative_rule"
    assert row["binding_force"] == "binding"
    assert row["legal_status"] == "effective"
    assert row["identity_us"]["fr_rin"] == ["2137-AF20"]
    # FR 官方身份生效后 missing 应显著减少
    assert len(row["legal_identity"]["missing_fields"]) <= 2


def test_completeness_before_after():
    records = [_rec("us_fr_2019-03812"), _rec("us_fr_2024-09094")]
    before = record_completeness(records)
    after = record_completeness(records, fr_identities={
        "us_fr_2019-03812": FR_IDENTITY, "us_fr_2024-09094": FR_IDENTITY})
    assert before["complete"] == 0
    assert after["complete"] == 2
    assert after["pct"] > before["pct"]


# ------------------------------------------------------------ 增量合并 / dry-run

def test_merge_keeps_old_rows():
    """⚠️ 不用 pytest tmp_path：本机 %TEMP%\\pytest-of-* 目录有权限缺陷（WinError 5）。"""
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / "outputs") as td:
        path = Path(td) / "overlay.jsonl"
        old = {"evidence_id": "old-1", "acceptance_class": "A2"}
        write_overlay(path, {"old-1": old})
        assert load_jsonl(path)["old-1"]["acceptance_class"] == "A2"

        new_rows = [{"evidence_id": "new-1", "acceptance_class": "B"}]
        merged = merge_rows_into_overlay(load_jsonl(path), new_rows)
        write_overlay(path, merged)
        data = load_jsonl(path)
        assert set(data) == {"old-1", "new-1"}          # 旧行保留（增量）
        # 原文件内容可被 JSON 解析（无损坏）
        for line in path.read_text(encoding="utf-8").splitlines():
            json.loads(line)
