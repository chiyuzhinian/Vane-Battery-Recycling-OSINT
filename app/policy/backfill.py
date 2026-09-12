# -*- coding: utf-8 -*-
"""Policy Metadata Backfill（Phase 4B-1 Step 2）—— 纯逻辑，无网络。

设计（延续 Phase 4A §14“原始 evidence 不可变”）：
    · 不修改 outputs/*.jsonl；一切增量写 **overlay**
    · 本模块负责：记录装载 / 过滤（region·role·only-missing·limit）/
      overlay 行构建 / FR 身份合并 / before-after 完整度度量
    · 网络抓取在 scripts/enrich_us_identity.py（FR 单文档 API），与本模块解耦

测试：tests/phase4b1/test_identity_backfill.py
"""
from __future__ import annotations

import glob
import json
from datetime import datetime, timezone
from pathlib import Path

from app.policy.acceptance import classify_record
from app.policy.legal_identity import REQUIRED_FIELDS, resolve_identity
from app.policy.source_access import expand_role_sources

BACKFILL_VERSION = "phase4b1.v2"
COMPLETE_TOLERANCE = 2          # missing_fields ≤ 2 视为完整（与 Phase 4A 一致）


# ------------------------------------------------------------ 装载

def load_records(root: Path) -> list[dict]:
    """outputs/*.jsonl 去重装载（evidence_id 先见者胜出，与 Phase 4A 同口径）。"""
    rows: dict[str, dict] = {}
    for fp in glob.glob(str(root / "outputs" / "*.jsonl")):
        if Path(fp).name.startswith(("_", "review", "policy_metadata",
                                     "fr_identity")):
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


def load_jsonl(path: Path) -> dict[str, dict]:
    """读 overlay 类文件 → {evidence_id: row}。"""
    out: dict[str, dict] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("evidence_id"):
            out[row["evidence_id"]] = row
    return out


# ------------------------------------------------------------ 过滤

def region_of(record: dict) -> str:
    sid = str(record.get("source_id") or "")
    if sid in ("eur_lex", "eu_eurlex_battery_reg", "eu_eurlex_keyword",
               "eu_eurlex_elv", "eu_eurlex_waste_shipment", "eu_eurlex_crm") \
            or sid.startswith("eu_nim_") or record.get("region") == "EU":
        return "EU"
    if sid.startswith("us_") or sid.startswith(("browser_phmsa", "browser_bci",
                                                "browser_calrecycle")):
        return "US"
    return "OTHER"


def role_source_ids(role: str, alias_map: dict, known_source_ids: list[str]) -> list[str]:
    """角色名 → 真实 source_id 列表（经别名展开）。角色必须在注册表中。"""
    from app.policy.config import load_registry
    for j in load_registry().jurisdictions:
        for r in j.source_roles:
            if r.role == role:
                return expand_role_sources(list(r.sources), alias_map,
                                           known_source_ids)
    raise ValueError(f"注册表中不存在角色：{role}")


def filter_records(records: list[dict], *, region: str = "",
                   source_role: str = "", only_missing: bool = False,
                   limit: int = 0, alias_map: dict | None = None,
                   known_source_ids: list[str] | None = None,
                   evidence_prefix: str = "") -> list[dict]:
    out = records
    if evidence_prefix:
        out = [r for r in out
               if str(r.get("evidence_id") or "").startswith(evidence_prefix)]
    if region:
        out = [r for r in out if region_of(r) == region.upper()]
    if source_role:
        ids = set(role_source_ids(source_role, alias_map or {},
                                  known_source_ids or []))
        out = [r for r in out if str(r.get("source_id") or "") in ids]
    if only_missing:
        out = [r for r in out
               if len(resolve_identity(r).missing_fields) > COMPLETE_TOLERANCE]
    if limit and limit > 0:
        out = out[:limit]
    return out


# ------------------------------------------------------------ overlay 行

def effective_identity(record: dict, fr_identity: dict | None = None) -> dict:
    """基础身份 + FR 官方身份 → 有效身份（用于完整度度量与 overlay 落盘）。"""
    idn = resolve_identity(record)
    eff = {
        "canonical_id": idn.canonical_id,
        "jurisdiction": idn.jurisdiction,
        "official_title": idn.official_title,
        "instrument_type": idn.instrument_type,
        "binding_force": idn.binding_force,
        "official_identifier": idn.official_identifier,
        "official_url": idn.official_url,
        "status": idn.status,
        "issuer": idn.issuer,
        "language": idn.language,
    }
    if fr_identity:
        eff["canonical_id"] = fr_identity.get("canonical_id") or eff["canonical_id"]
        eff["official_identifier"] = (fr_identity.get("official_identifier")
                                      or eff["official_identifier"])
        eff["issuer"] = fr_identity.get("issuer") or eff["issuer"]
        eff["instrument_type"] = (fr_identity.get("instrument_type")
                                  or eff["instrument_type"])
        eff["binding_force"] = (fr_identity.get("binding_force")
                                or eff["binding_force"])
        st = fr_identity.get("legal_status")
        if st and st != "unknown":
            eff["status"] = st
    return eff


def _missing_of(eff: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS
            if not eff.get(f) or eff.get(f) == "unknown"]


def build_overlay_row(record: dict, *, fr_identity: dict | None = None) -> dict:
    """构建 overlay 行（Phase 4A 字段 + Step 2 的 FR 身份块）。"""
    res = classify_record(record)
    eff = effective_identity(record, fr_identity)
    row = {
        "evidence_id": record.get("evidence_id"),
        "acceptance_class": res.classification,
        "acceptance_relevant": res.relevant,
        "acceptance_confidence": round(res.confidence, 3),
        "topic_ids": res.topic_ids,
        "acceptance_reasons": res.reason_codes,
        "evidence_quotes": res.evidence_quotes[:3],
        "acceptance_review": res.requires_human_review,
        "instrument_type": eff["instrument_type"],
        "binding_force": eff["binding_force"],
        "legal_status": eff["status"],
        "legal_identity": {
            "canonical_id": eff["canonical_id"],
            "jurisdiction": eff["jurisdiction"],
            "issuer": eff["issuer"],
            "official_identifier": eff["official_identifier"],
            "language": eff["language"],
            "missing_fields": _missing_of(eff),
        },
        "backfill_version": BACKFILL_VERSION,
        "backfilled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if fr_identity:
        row["identity_us"] = fr_identity
    return row


def merge_rows_into_overlay(overlay: dict[str, dict], rows: list[dict]) -> dict[str, dict]:
    """增量合并写（保留不在本次处理范围的旧行）。"""
    merged = dict(overlay)
    for r in rows:
        merged[r["evidence_id"]] = r
    return merged


def write_overlay(path: Path, rows: dict[str, dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


# ------------------------------------------------------------ 度量

def record_completeness(records: list[dict],
                        fr_identities: dict[str, dict] | None = None) -> dict:
    """[{evidence_id, effective_identity}] → 完整度（missing ≤ 容差 即完整）。"""
    fr_identities = fr_identities or {}
    total = len(records)
    complete = 0
    incomplete_ids: list[str] = []
    for r in records:
        eff = effective_identity(r, fr_identities.get(r.get("evidence_id")))
        if len(_missing_of(eff)) <= COMPLETE_TOLERANCE:
            complete += 1
        else:
            incomplete_ids.append(str(r.get("evidence_id")))
    return {"total": total, "complete": complete,
            "pct": round(100.0 * complete / total, 1) if total else 0.0,
            "incomplete_ids": incomplete_ids[:50]}


def backfill_report(before: dict, after: dict, *, failed: int = 0,
                    ambiguous: int = 0,
                    human_review_required: int = 0) -> dict:
    """规格 §12 要求的 before/after/failed/ambiguous/human review 摘要。"""
    return {
        "before_completeness": {"total": before["total"],
                                "complete": before["complete"],
                                "pct": before["pct"]},
        "after_completeness": {"total": after["total"],
                               "complete": after["complete"],
                               "pct": after["pct"]},
        "delta_pct": round(after["pct"] - before["pct"], 1),
        "failed": failed,
        "ambiguous": ambiguous,
        "human_review_required": human_review_required,
    }
