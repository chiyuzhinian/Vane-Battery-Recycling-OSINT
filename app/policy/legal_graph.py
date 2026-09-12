# -*- coding: utf-8 -*-
"""Legal Family Graph（Phase 4A §8）。

对核心 P0 法案执行**家族扩张**检查：
    SUPPLEMENTS / IMPLEMENTS / AMENDS / CORRECTS(CORRIGENDUM_OF) /
    REPEALS / REPLACED_BY / TRANSPOSES(IMPLEMENTS_NATIONALLY) /
    REFERENCES / DERIVED_FROM(proposal 系)

纪律：发现 core act ≠ 覆盖完成；family 未解决 → 饱和门不过。
输出：outputs/audit/legal_family_status.json
"""
from __future__ import annotations

import glob
import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "outputs"
AUDIT_DIR = OUT / "audit"

# P0 根法案（family expansion 的起点）
P0_ROOTS = {
    "32023R1542": {"name": "EU 电池法", "kind": "regulation",
                   "expected": ["SUPPLEMENTS", "IMPLEMENTS", "AMENDS",
                                "CORRIGENDUM_OF", "RELATED_PROPOSAL"]},
    "32000L0053": {"name": "ELV 报废车辆指令", "kind": "directive",
                   "expected": ["TRANSPOSES", "AMENDS", "CORRIGENDUM_OF"]},
    "32024R1157": {"name": "废物运输条例（黑粉跨境）", "kind": "regulation",
                   "expected": ["SUPPLEMENTS", "AMENDS", "RELATED_PROPOSAL"]},
    "32006L0066": {"name": "电池指令（旧）", "kind": "directive",
                   "expected": ["TRANSPOSES", "AMENDS", "REPEALS"]},
}

# 关系识别（标题级；与 EUR-Lex 措辞对齐）
_REL_PATTERNS = [
    ("CORRIGENDUM_OF", re.compile(r"^\s*corrigendum\s+to", re.I)),
    ("SUPPLEMENTS", re.compile(r"\bsupplementing\b", re.I)),
    ("IMPLEMENTS", re.compile(r"\bimplementing\b|\blaying\s+down\s+rules\s+for\s+the\s+application\b", re.I)),
    ("AMENDS", re.compile(r"\bamending\b", re.I)),
    ("REPEALS", re.compile(r"\brepealing\b", re.I)),
    ("REPLACED_BY", re.compile(r"\breplacing\b", re.I)),
    ("TRANSPOSES", re.compile(r"\btranspos", re.I)),
]


@dataclass
class FamilyStatus:
    root_act: str
    root_name: str
    expected_relation_types: list[str] = field(default_factory=list)
    found_relations: dict = field(default_factory=dict)
    unresolved_relations: list[str] = field(default_factory=list)
    family_completeness: float = 0.0
    members_total: int = 0
    national_transpositions: int = 0
    # ---- Step 7：官方关系（Cellar SPARQL）----
    official_relations: dict = field(default_factory=dict)
    resolved_official: list[str] = field(default_factory=list)
    absent_official: list[str] = field(default_factory=list)


OFFICIAL_FILE = AUDIT_DIR / "legal_family_official.json"


def load_official_relations(path: Path | None = None) -> dict:
    """读 outputs/audit/legal_family_official.json（refresh_legal_family.py 产物）。

    返回 {root_celex: {RELATION: [{celex,date,uri}]}}；文件缺失时返回空 dict（向后兼容）。
    """
    fp = path or OFFICIAL_FILE
    if not fp.exists():
        return {}
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    roots = data.get("roots") or {}
    # 文件结构：{root: {work, relations:{REL:[...]}}} → 规整为 {root: {REL:[...]}}
    out: dict[str, dict] = {}
    for root, entry in roots.items():
        if isinstance(entry, dict) and "relations" in entry:
            out[root] = entry.get("relations") or {}
        elif isinstance(entry, dict):
            out[root] = entry
    return out


def _load_records() -> list[dict]:
    rows: dict[str, dict] = {}
    for fp in glob.glob(str(OUT / "*.jsonl")):
        if Path(fp).name.startswith(("_", "review")):
            continue
        for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            eid = r.get("evidence_id")
            if eid and eid not in rows:
                rows[eid] = r
    return list(rows.values())


def _mentions_root(record: dict, root_celex: str) -> bool:
    """记录是否属于 root 的家族（标题含法规号 / meta.celex 派生 / NIM directive）。"""
    t = record.get("title") or ""
    meta = record.get("meta") or {}
    # 32023R1542 → "2023/1542"；32000L0053 → "2000/53"
    m = re.match(r"3(\d{4})([RLD])(\d{4})", root_celex)
    short = f"{m.group(1)}/{m.group(3)}".lstrip("0") if m else root_celex
    if short and short in t:
        return True
    celex = str(meta.get("celex") or "")
    if celex and celex.startswith(root_celex[:7]) and celex != root_celex:
        # 同族 CELEX（如 32023R1542R(05) 更正版）
        return True
    if meta.get("base") == root_celex:
        return True
    if str(record.get("source_id") or "").startswith("eu_nim_"):
        if str(meta.get("directive") or "") == root_celex:
            return True
    return False


def build_family_status(official: dict | None = None) -> list[FamilyStatus]:
    # Step 7：官方关系（Cellar）—— 未传入时自动读取审计产物（缺失则不合并）
    if official is None:
        official = load_official_relations()
    from app.policy.family_official import merge_family
    records = _load_records()
    out: list[FamilyStatus] = []
    for root, info in P0_ROOTS.items():
        st = FamilyStatus(root, info["name"],
                          expected_relation_types=list(info["expected"]))
        found: dict[str, list[str]] = {}
        transpositions = 0
        for r in records:
            if not _mentions_root(r, root):
                continue
            st.members_total += 1
            if str(r.get("source_id") or "").startswith("eu_nim_"):
                transpositions += 1
                found.setdefault("TRANSPOSES", []).append(
                    r.get("evidence_id") or r.get("title", "")[:40])
                continue
            title = r.get("title") or ""
            for rel, rx in _REL_PATTERNS:
                if rx.search(title):
                    found.setdefault(rel, []).append(
                        r.get("evidence_id") or title[:40])
                    break
            # proposal（520xxPC / COM）→ RELATED_PROPOSAL
            if re.search(r"\b52\d{3}PC\d+|\bCOM\(\d{4}\)|proposal\s+for", title, re.I):
                found.setdefault("RELATED_PROPOSAL", []).append(
                    r.get("evidence_id") or title[:40])
        st.national_transpositions = transpositions
        st.found_relations = {k: v[:8] for k, v in found.items()}
        # ---- Step 7：官方关系合并 ----
        root_official = (official or {}).get(root, {})
        st.official_relations = {
            rel: (rows or [])[:12] for rel, rows in root_official.items()}
        merge = merge_family(expected=list(st.expected_relation_types),
                             corpus_found=set(found.keys()),
                             official=root_official)
        st.resolved_official = merge["resolved_official"]
        st.absent_official = merge["absent_official"]
        st.unresolved_relations = merge["unresolved"]
        st.family_completeness = merge["completeness"]
        out.append(st)
    return out


def write_family_audit() -> Path:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    statuses = build_family_status()
    payload = {
        "generated_at": "2026-09-12",
        "families": [asdict(s) for s in statuses],
        "summary": {
            "families": len(statuses),
            "fully_resolved": sum(1 for s in statuses
                                  if not s.unresolved_relations),
            "p0_unresolved_total": sum(len(s.unresolved_relations)
                                       for s in statuses),
        },
    }
    path = AUDIT_DIR / "legal_family_status.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path
