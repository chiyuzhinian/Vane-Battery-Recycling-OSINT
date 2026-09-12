# -*- coding: utf-8 -*-
"""Phase 4A — Policy Corpus Acceptance & Saturation。

模块地图：
    config.py           YAML 单一真源 → Pydantic → 运行时（fail-fast）
    instruments.py      文书类型 & 约束力判定
    acceptance.py       A1/A2/B/C/D 分类
    source_universe.py  管辖区 × 源角色 覆盖状态机
    legal_identity.py   文档级法律身份解析
    legal_graph.py      法律家族图 & 完整性
    goldset.py          Gold Set 评估
    saturation.py       SG1–SG9 饱和门
"""
