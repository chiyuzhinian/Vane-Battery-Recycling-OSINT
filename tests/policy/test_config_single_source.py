# -*- coding: utf-8 -*-
"""配置单一真源 & fail-fast 回归（Phase 4A §12）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.config import (  # noqa: E402
    Topic, config_status, load_acceptance, load_instruments,
    load_registry, load_topics, compiled_topics)


def test_all_configs_load():
    s = config_status()
    assert s["ok"], s["errors"]


def test_topic_ids_complete():
    topics = load_topics()
    ids = [t.id for t in topics.topics]
    assert ids == [f"T{i:02d}" for i in range(1, 15)]


def test_b_required_topics_exist():
    acceptance = load_acceptance()
    known = {t.id for t in load_topics().topics}
    for cls in acceptance.classes.values():
        for tid in cls.required_any_topics:
            assert tid in known, f"B 类要求的主题 {tid} 不在 ontology 中"


def test_instrument_priority_ids_exist():
    cfg = load_instruments()
    known = {i.id for i in cfg.instrument_types}
    for pid in cfg.priority:
        assert pid in known, f"优先级中的 {pid} 未定义"


def test_invalid_regex_fails_fast():
    with pytest.raises(Exception):
        Topic(id="TX", name_en="x", name_zh="x", include_patterns=["(unclosed"])


def test_compiled_topics_cache_matches_yaml():
    comp = compiled_topics()
    assert set(comp) == {t.id for t in load_topics().topics}


def test_registry_codes_unique():
    reg = load_registry()
    codes = [j.code for j in reg.jurisdictions]
    assert len(codes) == len(set(codes))
