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
    assert set(mod.CONNECTOR_MAP) >= {"SE", "PL", "FI", "US-CA", "US-WA"}
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


def test_us_state_connector_registry():
    from app.connectors.leginfo_ca import LeginfoCaConnector
    from app.connectors.rcw_wa import RcwWaConnector
    assert REGISTRY["us_ca_leginfo"] is LeginfoCaConnector
    assert REGISTRY["us_wa_rcw"] is RcwWaConnector
    assert len(LeginfoCaConnector.DEFAULT_DOCS) >= 4
    assert len(RcwWaConnector.DEFAULT_DOCS) >= 2


def test_us_state_artifacts():
    ca_files = sorted(glob.glob(str(ROOT / "outputs" / "jurisdiction_us-ca_*.jsonl")))
    wa_files = sorted(glob.glob(str(ROOT / "outputs" / "jurisdiction_us-wa_*.jsonl")))
    if not ca_files:
        pytest.skip("需先运行 collect_jurisdiction_sources.py --jurisdictions US-CA")
    ca_rows = [json.loads(ln) for ln in
               Path(ca_files[-1]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(ca_rows) >= 4
    assert all(r["source_id"] == "us_ca_leginfo" for r in ca_rows)
    assert all(r["region"] == "US" and r["meta"]["jurisdiction"] == "US-CA"
               for r in ca_rows)
    titles = " ".join(r["title"] for r in ca_rows)
    assert "AB 2440" in titles
    assert max(len(r["text"]) for r in ca_rows) > 10000      # AB2440 全文
    if wa_files:
        wa_rows = [json.loads(ln) for ln in
                   Path(wa_files[-1]).read_text(encoding="utf-8").splitlines()
                   if ln.strip()]
        assert all(r["source_id"] == "us_wa_rcw" for r in wa_rows)
        assert any("70A.200" in r["title"] or "70A.555" in r["title"]
                   for r in wa_rows)


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


def test_extract_next_flight_and_text_nodes():
    import json as _json

    from app.connectors.leg_utils import extract_next_flight, extract_text_nodes
    payload = _json.dumps('{"text":"Jätelaki 646/2011"}')
    payload2 = _json.dumps('{"text":"tuottajavastuu ja jäte"}')
    html = (f"<script>self.__next_f.push([1,{payload}])</script>"
            f"<script>self.__next_f.push([1,{payload2}])</script>")
    dec = extract_next_flight(html)
    assert "Jätelaki 646/2011" in dec and "tuottajavastuu" in dec
    nodes = extract_text_nodes(dec)
    assert "Jätelaki 646/2011" in nodes and "jäte" in nodes


def test_multilingual_topics_fi_pl_ee():
    from app.policy.acceptance import scan_topics
    fi = ("Jätelaki; tuottajavastuu ja keräysjärjestelmä; romuajoneuvo; "
          "vaarallisten aineiden kuljetus; vaarallinen jäte; kierrätys")
    pl = ("odpowiedzialność producenta; selektywna zbiórka; wycofane z eksploatacji; "
          "towarów niebezpiecznych; odpady niebezpieczne; recykling")
    ee = ("tootjavastutus; kogumine; vanasõiduk; ohtlike ainete vedu; "
          "ohtlikud jäätmed; taaskasutus")
    want = {"T01", "T02", "T03", "T05", "T07", "T10"}
    for text in (fi, pl, ee):
        ids, _ = scan_topics(text)
        missing = want - set(ids)
        assert not missing, f"多语种词表命中缺口 {missing}（text={text[:40]}…）"


def test_fi_artifact_after_flight_extraction():
    files = sorted(glob.glob(str(ROOT / "outputs" / "jurisdiction_fi_*.jsonl")))
    if not files:
        pytest.skip("需先运行 collect_jurisdiction_sources.py --jurisdictions FI")
    rows = [json.loads(ln) for ln in
            Path(files[-1]).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) >= 3
    assert all(r["source_id"] == "fi_finlex" for r in rows)
    assert all(r["region"] == "EU" and r["meta"]["jurisdiction"] == "FI"
               for r in rows)
    assert any(r["meta"]["acceptance_class"] in ("A1", "A2", "B", "C")
               for r in rows), "Jätelaki 应至少为 C（背景语料）"
    assert max(len(r["text"]) for r in rows) > 20000
