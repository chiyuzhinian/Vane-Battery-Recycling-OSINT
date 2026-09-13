# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 5：pilot 连接器 —— 解析工具 / 注册表 / 采集产物。

纪律：
    · 挑战页/JS 壳文本不得进语料（防伪造正文）
    · SOURCE_FAILURE ≠ 0 结果（失败必须留痕到 failures 产物）
"""
from __future__ import annotations

import glob
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import REGISTRY  # noqa: E402
from app.connectors.leg_utils import (  # noqa: E402
    detect_challenge, extract_title, find_iso_date, strip_html,
)

PILOT_SOURCES = ("se_sfst", "pl_isap", "fi_finlex")


def test_strip_html_and_title():
    html = ("<html><head><title>SFS 2008:834 — test</title>"
            "<script>var x=1;</script><style>.a{}</style></head>"
            "<body><h1>Förordning</h1><p>蝙蝠文本 A</p><p>text B</p></body></html>")
    text = strip_html(html)
    assert "var x" not in text and ".a" not in text
    assert "Förordning" in text and "text B" in text
    assert extract_title(html) == "SFS 2008:834 — test"
    assert extract_title("<html><body><h1>Only H1</h1></body></html>") == "Only H1"
    assert find_iso_date("公开日期 2026-09-13 生效") == "2026-09-13"


def test_detect_challenge():
    assert detect_challenge("<h1>Pardon Our Interruption</h1>") == "pardon_our_interruption"
    assert detect_challenge("... Just a moment...") == "cloudflare_challenge"
    assert detect_challenge("Access Denied: you lack permission") == "access_denied"
    assert detect_challenge("<p>普通法规正文 normal content</p>") == ""


def test_registry_and_default_docs():
    from app.connectors.finlex_fi import FinlexFiConnector
    from app.connectors.isap_pl import IsapPlConnector
    from app.connectors.sfst_se import SfstSeConnector
    for key, cls in (("se_sfst", SfstSeConnector), ("pl_isap", IsapPlConnector),
                     ("fi_finlex", FinlexFiConnector)):
        assert key in REGISTRY and REGISTRY[key] is cls
        assert cls.source_id == key
        assert len(cls.DEFAULT_DOCS) >= 3


def _load_collect_module():
    spec = importlib.util.spec_from_file_location(
        "collect_jurisdiction_sources",
        ROOT / "scripts" / "collect_jurisdiction_sources.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_connector_map_and_record_schema():
    mod = _load_collect_module()
    assert set(mod.CONNECTOR_MAP) >= {"SE", "PL", "FI"}
    from app.connectors.base import RawEvidence
    ev = RawEvidence(evidence_id="se_sfst_test", channel="connector",
                     source_id="se_sfst", source_url="https://x",
                     source_title="测试法条（电池）", publish_date=None,
                     raw_text="waste battery recycling 电池回收 test",
                     meta={"doc_key": "SE:SFS:test"})
    rec = mod.to_record(ev, "SE", "EU")
    for key in ("evidence_id", "source_id", "region", "meta", "text",
                "relevant", "relevance_score", "hits"):
        assert key in rec, key
    assert rec["region"] == "EU"
    assert rec["meta"]["jurisdiction"] == "SE"
    assert rec["meta"]["acceptance_class"] in ("A1", "A2", "B", "C", "D")


def test_se_artifact_and_junk_guard():
    files = sorted(glob.glob(str(ROOT / "outputs" / "jurisdiction_*.jsonl")))
    if not files:
        pytest.skip("需先运行 collect_jurisdiction_sources.py --jurisdictions SE")
    # 防伪造：任何落盘语料不得包含挑战页/JS 壳标记
    for fp in files:
        text = Path(fp).read_text(encoding="utf-8", errors="replace")[:60000]
        assert detect_challenge(text) == "", f"挑战页文本进入语料：{fp}"
    se_files = [f for f in files if "jurisdiction_se_" in f]
    assert se_files, "缺 SE 语料"
    rows = [json.loads(ln) for ln in
            Path(se_files[-1]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) >= 3
    for r in rows:
        assert r["source_id"] == "se_sfst"
        assert r["region"] == "EU" and r["meta"]["jurisdiction"] == "SE"
        assert len(r["text"]) > 2000


def test_failures_artifact_records_pl_fi():
    fp = ROOT / "outputs" / "audit" / "jurisdiction_collection_failures.json"
    if not fp.exists():
        pytest.skip("需先运行采集脚本（PL/FI 失败入档）")
    entries = json.loads(fp.read_text(encoding="utf-8"))["entries"]
    jids = {e["jurisdiction"] for e in entries}
    assert {"PL", "FI"} <= jids
    assert all(e["error"] for e in entries)
