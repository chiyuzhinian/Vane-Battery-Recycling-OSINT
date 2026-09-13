# -*- coding: utf-8 -*-
"""Identity Hardening（Phase 4B-2B0 Step 2）—— 身份构造与完整度分解。

背景（2B0 审计 Q4/P0-A3）：
    · pilot 专线 identity 统计被 discovery-layer（NIM）稀释；
    · 历史专线记录（DE/NL/ES/FR）没有 identity——但 meta 里有**官方编号**；
    · overlay（fr_identity_overlay / policy_metadata_overlay）无人合并。

本模块：
    build_identity_v2(record)         从官方编号 meta 构造 identity（不猜）
    effective_identity(record, rows)  record.identity → v2 构造 → overlay
    identity_v2_completeness(...)     核心 5 字段口径的完整度
    decompose_identity(...)           new / historical / discovery 分解

核心字段（规格 §七；5 字段判定 + 增强字段尽力给）：
    canonical_id · official_identifier · issuer · language · official_url
    增强：instrument_type / binding_force / legal_status / publication_date
         / effective_date（仅当官方元数据直接提供，缺失留空——**禁止默认值**）

构造规则（全部来自 meta 或 title 的官方编号；测试锁定）：
    de_gesetze       slug        → DE:GIW:{slug}
    nl_bwb           bwb_id      → NL:BWB:{bwb_id}
    es_boe           boe_id      → ES:BOE:{boe_id}（derogada→repealed）
    fr_ademe_opendata dataset_id → FR:ADEME:{dataset_id}（supporting dataset）
    fr_dila          dataset+evidence_id → FR:{dataset}:{eid}（**本地稳定 id**，
                     official_identifier 从 title 提取（"n° 2021-950"）——
                     提取不到即留空，不猜）
"""
from __future__ import annotations

import re

from app.policy.identity_jurisdiction import ISSUERS, identity_from_meta

#: 完整度判定的核心字段（规格 §七）
CORE_FIELDS = ("canonical_id", "official_identifier", "issuer", "language",
               "official_url")
#: 增强字段（可用即填，缺失不罚）
ENHANCE_FIELDS = ("instrument_type", "binding_force", "legal_status",
                  "publication_date", "effective_date")

_OFFICIAL_ID_RE = re.compile(r"n[°ºo]\s*([\d][\d\-–]+)")
_DATE_ID_RE = re.compile(r"\bdu\s+\d{1,2}\s+\w+\s+\d{4}")

#: 源 → 语言（官方语言体系中确定）
_LANG_BY_SOURCE = {
    "de_gesetze": "de", "nl_bwb": "nl", "es_boe": "es",
    "fr_ademe_opendata": "fr", "fr_dila": "fr",
}


def _title_official_id(title: str) -> str:
    """title → 官方编号（仅明确模式：Décret n° 2021-950 / du 28 juillet 2026）。"""
    t = title or ""
    m = _OFFICIAL_ID_RE.search(t)
    if m:
        return m.group(1)
    m = _DATE_ID_RE.search(t)
    return m.group(0).replace("du ", "") if m else ""


def build_identity_v2(record: dict) -> dict | None:
    """从官方编号 meta 构造 identity；不可构造（无官方编号）→ None。"""
    meta = record.get("meta") or {}
    sid = str(record.get("source_id") or "")
    base = identity_from_meta(meta)
    if base:
        out = dict(base)
        out.setdefault("official_url",
                       meta.get("official_url") or record.get("url") or "")
        return out
    out: dict = {}
    if sid == "de_gesetze" and meta.get("slug"):
        slug = str(meta["slug"])
        out = {"canonical_id": f"DE:GIW:{slug}",
               "official_identifier": slug,
               "official_url":
                   f"https://www.gesetze-im-internet.de/{slug}/"}
    elif sid == "nl_bwb" and meta.get("bwb_id"):
        bwb = str(meta["bwb_id"])
        out = {"canonical_id": f"NL:BWB:{bwb}",
               "official_identifier": bwb,
               "official_url": meta.get("work_url")
               or f"https://wetten.overheid.nl/{bwb}"}
    elif sid == "es_boe" and meta.get("boe_id"):
        boe = str(meta["boe_id"])
        out = {"canonical_id": f"ES:BOE:{boe}",
               "official_identifier": boe,
               "official_url": meta.get("url_eli")
               or f"https://www.boe.es/buscar/act.php?id={boe}"}
        if meta.get("derogada"):
            out["legal_status"] = "repealed"
        if meta.get("fecha_vigencia"):
            out["effective_date"] = str(meta["fecha_vigencia"])
    elif sid == "fr_ademe_opendata" and meta.get("dataset_id"):
        ds = str(meta["dataset_id"])
        out = {"canonical_id": f"FR:ADEME:{ds}",
               "official_identifier": ds,
               "official_url": record.get("url") or ""}
    elif sid == "fr_dila":
        dataset = str(meta.get("dataset") or "LEGI")
        eid = str(record.get("evidence_id") or "")
        out = {"canonical_id": f"FR:{dataset}:{eid}",   # 本地稳定 id（注明）
               "official_identifier": _title_official_id(
                   record.get("title") or ""),          # 提取不到即空
               "official_url": meta.get("archive_url")
               or record.get("url") or ""}
    if not out:
        return None
    out["jurisdiction"] = {"de_gesetze": "DE", "nl_bwb": "NL", "es_boe": "ES",
                           "fr_ademe_opendata": "FR", "fr_dila": "FR"}.get(
                               sid, "")
    out["issuer"] = ISSUERS.get(out["jurisdiction"], "")
    out["language"] = _LANG_BY_SOURCE.get(sid, "")
    out["source_role"] = meta.get("source_role", "")
    out["identity_source"] = "constructed_v2"
    return out


def effective_identity(record: dict, overlay: dict | None = None) -> dict | None:
    """身份合并：v2 构造（编号规则） ⊕ 既有 identity 字段 → 补 URL。

    · 既有 identity 字段优先（更早写入、经 backfill 审核）；
    · v2 只补**缺失字段**（如旧记录缺 official_url）；
    · overlay（legal_identity）作为最后回退；先见者胜出防覆盖。
    """
    v2 = build_identity_v2(record) or {}
    ident = record.get("identity") or {}
    merged: dict = {}
    for part in (v2, ident):           # ident 后写 → 优先级更高
        for k, v in (part or {}).items():
            if v and not merged.get(k):
                merged[k] = v
    if not merged.get("canonical_id") and overlay:
        row = overlay.get(str(record.get("evidence_id") or "")) or {}
        ov = row.get("legal_identity") or row.get("identity") or {}
        for k, v in ov.items():
            if v and not merged.get(k):
                merged[k] = v
    if not merged.get("official_url"):
        merged["official_url"] = ((record.get("meta") or {}).get("official_url")
                                  or record.get("url") or "")
    return merged if merged.get("canonical_id") else None


def identity_v2_completeness(records: list[dict], jid: str,
                             overlay: dict | None = None) -> dict:
    """专线 corpus 的核心 5 字段完整度（effective identity 口径）。"""
    from app.policy.identity_jurisdiction import is_dedicated_source
    from app.policy.jurisdiction_map import jurisdiction_of
    full = total = 0
    missing: list[dict] = []
    for r in records:
        if not is_dedicated_source(str(r.get("source_id") or "")):
            continue
        if jurisdiction_of(r) != jid:
            continue
        total += 1
        ident = effective_identity(r, overlay) or {}
        lacks = [f for f in CORE_FIELDS if not ident.get(f)]
        if not lacks:
            full += 1
        else:
            missing.append({"evidence_id": r.get("evidence_id"),
                            "source_id": r.get("source_id"),
                            "lacks": lacks})
    return {"total": total, "complete": full,
            "pct": round(100.0 * full / total, 1) if total else 0.0,
            "missing": missing[:30]}


def decompose_identity(records: list[dict], jid: str,
                       overlay: dict | None = None) -> dict:
    """new / historical / discovery-layer 三分解（规格 §七 必须区分）。"""
    from app.policy.identity_jurisdiction import is_dedicated_source
    from app.policy.jurisdiction_map import jurisdiction_of
    out = {"new": {"total": 0, "complete": 0, "missing": []},
           "historical": {"total": 0, "complete": 0, "missing": []},
           "discovery_layer_excluded": 0}
    for r in records:
        if jurisdiction_of(r) != jid:
            continue
        if not is_dedicated_source(str(r.get("source_id") or "")):
            out["discovery_layer_excluded"] += 1
            continue
        bucket = "new" if (r.get("meta") or {}).get("discovered_by_round") \
            else "historical"
        ident = effective_identity(r, overlay) or {}
        lacks = [f for f in CORE_FIELDS if not ident.get(f)]
        out[bucket]["total"] += 1
        if not lacks:
            out[bucket]["complete"] += 1
        else:
            out[bucket]["missing"].append(
                {"evidence_id": r.get("evidence_id"),
                 "source_id": r.get("source_id"), "lacks": lacks})
    for b in ("new", "historical"):
        t = out[b]["total"]
        out[b]["pct"] = round(100.0 * out[b]["complete"] / t, 1) if t else None
    return out
