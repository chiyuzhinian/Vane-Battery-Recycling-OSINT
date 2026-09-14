# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 8：管辖地轮运行器 —— plan 装载 / 引用模式 / 抽取过滤。"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from app.policy.search_plan import load_plan, validate_plan  # noqa: E402
import run_jurisdiction_round as rj  # noqa: E402

PLANS = ("SE_PLAN_V1", "FI_PLAN_V1", "US_CA_PLAN_V1", "US_WA_PLAN_V1",
         "US_WA_PLAN_V2")


@pytest.mark.parametrize("plan_id", PLANS)
def test_plan_loads_and_scope_matches_jurisdiction(plan_id: str):
    plan = load_plan(plan_id)
    assert plan.scope == plan.jurisdiction
    assert plan.jurisdiction in rj.SUPPORTED
    validate_plan(plan)                      # 不抛异常
    assert plan.plan_hash() == load_plan(plan_id).plan_hash()   # 稳定


def test_plan_hashes_are_frozen():
    """hash 冻结承诺：与提交时一致（变化说明搜索空间被改，必须新 plan）。"""
    expect = {
        "SE_PLAN_V1": "80f3d13818c8",
        "FI_PLAN_V1": "bd138f120fb1",
        "US_CA_PLAN_V1": "391507348e01",
        "US_WA_PLAN_V1": "192be6abc2f2",
        "US_WA_PLAN_V2": "69a4f37344f0",   # Step 6：+D 路线（reset 独立视图）
    }
    for pid, prefix in expect.items():
        assert load_plan(pid).plan_hash().startswith(prefix), \
            f"{pid} plan_hash 变化 → 必须新建 plan（V2）并 reset"


def test_cite_patterns_extract_expected_docs():
    assert rj._cite_to_doc("SE", rj.CITE_PATTERNS["SE"].search(
        "enligt SFS 2008:834")) == "2008:834"
    assert rj._cite_to_doc("FI", rj.CITE_PATTERNS["FI"].search(
        "säädetty 646/2011 nojalla")) == "20110646"
    m = rj.CITE_PATTERNS["US-CA"].search(
        "Section 42451 of the Public Resources Code")
    assert rj._cite_to_doc("US-CA", m) == "PRC:42451"
    assert rj._cite_to_doc("US-WA", rj.CITE_PATTERNS["US-WA"].search(
        "under RCW 70A.555.010")) == "70A.555.010"


def test_extract_cited_only_uses_own_rows():
    records = [
        {"evidence_id": "se_sfst_2008_834", "title": "SFS 2008:834",
         "text": "hänvisar till SFS 1998:808", "meta": {"jurisdiction": "SE"}},
        # NIM 元数据（无 jurisdiction）→ 噪声源，不得抽取
        {"evidence_id": "eu_nim_se_x", "title": "NIM abstract",
         "text": "see SFS 2020:614 and mehr", "meta": {}},
        {"evidence_id": "de_gesetze_x", "title": "DE law",
         "text": "SFS 2001:999", "meta": {"jurisdiction": "DE"}},
    ]
    docs = rj._extract_cited("SE", records, set())
    # 仅自有记录（title+text）参与：2008:834（title）、1998:808（text）
    assert docs == ["2008:834", "1998:808"]
    assert "2020:614" not in docs      # NIM 元数据被过滤
    assert "2001:999" not in docs      # 其他管辖地记录被过滤


def test_doc_not_found_is_distinct_from_failure():
    assert issubclass(rj.DocNotFound, Exception)
    # 路线完全体：四个管辖地均有 fetch 实现
    assert set(rj.FETCHERS) == {"SE", "FI", "US-CA", "US-WA"}
    # 检索仅 SE/FI 具备（CA/WA 无检索端点，如实）
    assert set(rj.SEARCHERS) == {"SE", "FI"}


def test_round_records_and_persisted_corpus_exist():
    rounds = glob.glob(str(ROOT / "outputs" / "discovery_rounds" /
                           "round_SE_1_*.json"))
    if not rounds:
        pytest.skip("需先运行 run_jurisdiction_round.py")
    data = json.loads(Path(sorted(rounds)[-1]).read_text(encoding="utf-8"))
    assert data["round_mode"] == "discovery_expansion"
    assert data["plan_id"] == "SE_PLAN_V1"
    assert data["plan_hash"].startswith("80f3d13818c8")
    assert data["totals"]["new_unique_accepted_count"] >= 1
    pf = ROOT / "outputs" / data["persisted_file"]
    assert pf.exists()
    recs = [json.loads(x) for x in pf.read_text(encoding="utf-8").splitlines()
            if x.strip()]
    assert recs and all(r["meta"]["jurisdiction"] == "SE" for r in recs)


def test_mode_b_convergence_artifacts():
    """MODE B（§Step 9）：四地 streak≥2 收敛；MODE B 轮全 FULL 且零新增。"""
    fj = ROOT / "outputs" / "audit" / "jurisdiction_convergence.json"
    if not fj.exists():
        pytest.skip("需先运行 scripts/audit_jurisdiction_convergence.py")
    data = json.loads(fj.read_text(encoding="utf-8"))
    plans = data["plans"]
    assert set(plans) == {"SE_PLAN_V1", "FI_PLAN_V1", "US_CA_PLAN_V1",
                          "US_WA_PLAN_V1"}
    for pid, e in plans.items():
        c = e["convergence"]
        assert c["converged"] is True, pid
        assert c["streak"] >= 2, pid
        assert c["blocked_by_high_value"] is False, pid
        assert e["modeb_rounds"] >= 2, pid
        assert e["new_accepted_sum_modeB"] == 0, pid   # MODE B 零新增
        assert e["invalid"] == 0, pid
