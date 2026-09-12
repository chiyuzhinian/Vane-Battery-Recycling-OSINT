# -*- coding: utf-8 -*-
"""Phase 4B-1 Step 2：源别名对账回归（逻辑源名 → 真实 source_id）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import load_aliases, load_registry  # noqa: E402
from app.policy.source_access import (  # noqa: E402
    expand_role_sources, expand_source_patterns,
)

KNOWN = ["eu_nim_cz", "eu_nim_be", "eu_nim_nl", "eur_lex",
         "eu_eurlex_battery_reg", "eu_eurlex_keyword", "us_federal_register"]


def test_aliases_cover_known_drift():
    cfg = load_aliases()
    for key in ("eu_nim", "eu_eurlex_waste_shipment"):
        assert key in cfg.aliases, key
        assert cfg.aliases[key].patterns


def test_alias_keys_exist_in_registry():
    """fail-fast：别名键必须真的是注册表中的逻辑源名，否则是拼写漂移。"""
    registry_sources: set[str] = set()
    for j in load_registry().jurisdictions:
        for r in j.source_roles:
            registry_sources.update(r.sources)
        for entry in (j.countries + j.states):
            registry_sources.update(entry.get("sources", []))
    unknown = [k for k in load_aliases().aliases if k not in registry_sources]
    assert unknown == [], f"别名键不在注册表：{unknown}"


def test_wildcard_expansion():
    assert expand_source_patterns(["eu_nim_*"], KNOWN) == [
        "eu_nim_cz", "eu_nim_be", "eu_nim_nl"]
    assert expand_source_patterns(["us_federal_register"], KNOWN) == [
        "us_federal_register"]


def test_role_expansion_and_dedupe():
    alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
    ids = expand_role_sources(["eu_eurlex_waste_shipment", "eur_lex"],
                              alias_map, KNOWN)
    assert "eu_eurlex_battery_reg" in ids and "eu_eurlex_keyword" in ids
    assert "eur_lex" in ids
    assert len(ids) == len(set(ids))            # 去重
    # 未登记别名 → 原样保留
    assert expand_role_sources(["unknown_src"], alias_map, KNOWN) == ["unknown_src"]


def test_nim_role_expansion_matches_real_ids():
    """注册表 EURLEX_NIM 的 eu_nim 逻辑名 → 真实 eu_nim_* 国别 id。"""
    alias_map = {k: v.model_dump() for k, v in load_aliases().aliases.items()}
    ids = expand_role_sources(["eu_nim"], alias_map, KNOWN)
    assert set(ids) == {"eu_nim_cz", "eu_nim_be", "eu_nim_nl"}
