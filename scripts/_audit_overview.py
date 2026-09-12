# -*- coding: utf-8 -*-
"""仓库审计辅助：速览模块结构（docstring + 顶层定义）。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

TARGETS = [
    "app/core/feedback.py",
    "app/core/coverage.py",
    "app/core/authenticity.py",
    "app/connectors/base.py",
    "app/api/store.py",
    "scripts/audit_collection_coverage.py",
]

for rel in TARGETS:
    p = ROOT / rel
    if not p.exists():
        print(f"❌ 缺失 {rel}")
        continue
    src = p.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    doc = ast.get_docstring(tree) or ""
    print("=" * 100)
    print(f"# {rel}  ({len(src.splitlines())} 行)")
    print("─" * 4, "docstring 首段:")
    for line in doc.splitlines()[:12]:
        print("   ", line)
    defs = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            defs.append(f"{kind} {node.name}")
    print("─" * 4, "顶层定义:", ", ".join(defs[:40]))
    print()
