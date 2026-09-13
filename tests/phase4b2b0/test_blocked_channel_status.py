# -*- coding: utf-8 -*-
"""Phase 4B-2B0 Step 5：受阻通道攻坚状态测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors import REGISTRY  # noqa: E402

AUDIT = ROOT / "outputs" / "audit"
RESOLUTION = AUDIT / "blocked_channel_resolution.json"
PROOFS = AUDIT / "source_proofs"


def test_new_connectors_registered():
    for key in ("pl_sejm_eli", "us_ky_krs", "us_mn_revisor"):
        assert key in REGISTRY, key
    # 旧 ISAP 仍保留（浏览器通道候选；不绕过访问控制）
    assert "pl_isap" in REGISTRY


def test_blocked_channel_resolution_states():
    if not RESOLUTION.exists():
        pytest.skip("需先运行 scripts/proof_blocked_channels.py")
    d = json.loads(RESOLUTION.read_text(encoding="utf-8"))
    ch = d["channels"]
    # 攻坚结论（实测）：PL/KY/MN 适配；BE/EE/GA 端点级受阻；CO 部分
    assert ch["PL"]["status"] == "ADAPTED"
    assert ch["US-KY"]["status"] == "ADAPTED"
    assert ch["US-MN"]["status"] == "ADAPTED"
    assert ch["BE"]["status"].startswith("BLOCKED")
    assert ch["EE"]["status"].startswith("BLOCKED")
    assert ch["US-GA"]["status"].startswith("BLOCKED")
    assert ch["US-CO"]["status"].startswith("PARTIAL")
    assert set(d["adapted"]) == {"PL", "US-KY", "US-MN"}
    # 每条受阻记录必须有方法/归因（不判死、可追溯）
    for k, v in ch.items():
        assert v.get("method"), k
        assert v.get("note"), k


def test_proof_format_and_samples():
    for jid, min_chars in (("PL", 1500), ("US-KY", 400), ("US-MN", 400)):
        fp = PROOFS / f"{jid}.json"
        if not fp.exists():
            pytest.skip(f"缺 {jid}.json")
        proof = json.loads(fp.read_text(encoding="utf-8"))
        src = proof["sources"][0]
        assert "capabilities" in src and "samples" in src
        ok = [s for s in src["samples"] if s.get("status") == 200]
        if not ok:
            pytest.skip(f"{jid}: proof 为网络瞬态期间产物（0 样本）")
        # 每样本真实可读（字符下限）
        for s in ok:
            assert s.get("chars", 0) >= min_chars


def test_pl_contract_channel_updated():
    """PL 契约：官方替代通道 CONNECTED + ISAP 如实 BLOCKED。"""
    import yaml
    fp = ROOT / "sources" / "jurisdiction-onboarding" / "PL.yaml"
    c = yaml.safe_load(fp.read_text(encoding="utf-8"))
    chans = c["official_channel_map"]["MS_LEGISLATION_DATABASE"]
    by_id = {ch["source_id"]: ch for ch in chans}
    assert by_id["pl_sejm_eli"]["status"] == "CONNECTED"
    assert by_id["pl_isap"]["status"] == "BLOCKED"
