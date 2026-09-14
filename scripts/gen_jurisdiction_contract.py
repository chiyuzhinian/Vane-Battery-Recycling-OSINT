# -*- coding: utf-8 -*-
"""gen_jurisdiction_contract.py —— Phase 4B-2B §5：Contract 生成器。

从 outputs/audit/source_proofs/{JID}.json 生成
sources/jurisdiction-onboarding/{JID}.yaml 骨架：
  · official_channel_map ← proof.sources（status 映射：
      ACCESSIBLE+样本>0 → CONNECTED；ACCESSIBLE+样本=0 → PARTIAL；
      其他 → BLOCKED）
  · known_gaps ← 各 source 的 known_limitations / 探测错误
  · mandatory_source_roles ← EU/US 角色模板（§6）

用法：
  py scripts/gen_jurisdiction_contract.py AT CZ HU IT SK US-MI ...
  py scripts/gen_jurisdiction_contract.py --overwrite AT ...
（已存在文件默认不覆盖；人工精修备注可后续直接编辑 yaml。）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

PROOFS = ROOT / "outputs" / "audit" / "source_proofs"
CONTRACTS = ROOT / "sources" / "jurisdiction-onboarding"

EU_ROLES = ["MS_LEGISLATION_DATABASE", "MS_OFFICIAL_GAZETTE",
            "MS_ENVIRONMENT_MINISTRY_OR_AGENCY", "MS_WASTE_REGULATOR",
            "MS_TRANSPORT_OR_DANGEROUS_GOODS", "MS_CUSTOMS_OR_TRADE",
            "MS_STANDARDS_METADATA"]
US_ROLES = ["STATE_LEGISLATURE", "STATE_STATUTES", "STATE_ADMIN_CODE",
            "STATE_REGISTER", "STATE_ENVIRONMENT_AGENCY",
            "STATE_WASTE_PROGRAM", "STATE_BATTERY_EPR_OR_STEWARDSHIP",
            "STATE_TRANSPORT_HAZMAT"]

#: proof 源侧使用的别名 → 契约标准 role 名
ROLE_ALIAS = {
    "STATE_ENVIRONMENT": "STATE_ENVIRONMENT_AGENCY",
    "STATE_WASTE": "STATE_WASTE_PROGRAM",
    "STATE_BATTERY_EPR": "STATE_BATTERY_EPR_OR_STEWARDSHIP",
}

NAMES = {
    "AT": {"zh": "奥地利", "en": "Austria"},
    "CZ": {"zh": "捷克", "en": "Czechia"},
    "HU": {"zh": "匈牙利", "en": "Hungary"},
    "IT": {"zh": "意大利", "en": "Italy"},
    "SK": {"zh": "斯洛伐克", "en": "Slovakia"},
    "US-MI": {"zh": "密歇根", "en": "Michigan"},
    "US-IL": {"zh": "伊利诺伊", "en": "Illinois"},
    "US-TN": {"zh": "田纳西", "en": "Tennessee"},
    "US-TX": {"zh": "得克萨斯", "en": "Texas"},
    "US-NV": {"zh": "内华达", "en": "Nevada"},
    "US-OH": {"zh": "俄亥俄", "en": "Ohio"},
}

EU_LANGS = {"AT": "de", "CZ": "cs", "HU": "hu", "IT": "it", "SK": "sk",
            "BE": "nl/fr", "NL": "nl", "DE": "de", "FR": "fr", "ES": "es",
            "SE": "sv", "FI": "fi", "PL": "pl", "DK": "da"}


def _status_of(src: dict) -> tuple[str, str]:
    """proof source → (contract status, note)。"""
    st = src.get("status")
    samples_ok = sum(1 for s in src.get("samples") or []
                     if s.get("status") == 200)
    caps = src.get("capabilities") or {}
    if st == "BLOCKED":
        return "BLOCKED", "探测阶段全通道不可达/被拦截"
    if st == "ACCESSIBLE" and samples_ok > 0:
        return "CONNECTED", f"真实样本 {samples_ok} 条"
    if st == "ACCESSIBLE":
        return "PARTIAL", "入口可达但暂未取得合规样本"
    return "PARTIAL", f"status={st}"


def build_contract(jid: str, proof: dict) -> dict:
    is_us = jid.startswith("US-")
    roles = US_ROLES if is_us else EU_ROLES
    channels: dict[str, list] = {}
    gaps: list[str] = []
    covered: set[str] = set()
    for src in proof.get("sources") or []:
        role = str(src.get("source_role") or "UNKNOWN")
        role = ROLE_ALIAS.get(role, role)
        status, why = _status_of(src)
        entry = {
            "source_id": src.get("source_id"),
            "official_url": src.get("entry_url") or "",
            "access_method": src.get("access_method") or "html",
            "status": status,
            "note": (why + "；owner=" + str(src.get("official_owner") or ""))
                    if status != "CONNECTED" else why,
        }
        lim = src.get("known_limitations") or []
        if lim:
            entry["note"] += "；" + "；".join(str(x)[:120] for x in lim[:2])
        channels.setdefault(role, []).append(entry)
        if status == "BLOCKED":
            gaps.append(f"{role}: 探测不可达/被拦截（Batch 1 实证）")
    # 未覆盖的 mandatory 角色 → known_gaps（不得静默遗漏）
    gap_map: dict[str, str] = {}
    for role in roles:
        if role in channels:
            continue
        gap_map[role] = "Batch 1：未接入（Source Proof 未覆盖该角色）"
    for g in dict.fromkeys(gaps):
        role = g.split(":", 1)[0]
        gap_map[role] = g.split(":", 1)[1].strip()
    doc = {
        "version": 1,
        "jurisdiction_id": jid,
        "jurisdiction_name": NAMES.get(jid, {"zh": jid, "en": jid}),
        "level": "state" if is_us else "member_state",
        "official_languages": (
            ["en"] if is_us else [EU_LANGS.get(jid, "und")]),
        "source_proof": f"outputs/audit/source_proofs/{jid}.json"
                        f"（{proof.get('generated_at', '')[:10]}）",
        "mandatory_source_roles": roles,
        "official_channel_map": channels,
        "known_gaps": gap_map,
        "collector_strategy": {
            r: ("connector（html 解析）" if any(
                e["status"] in ("CONNECTED", "PARTIAL")
                for e in v) else "pending_probe")
            for r, v in channels.items()},
        "identity_strategy": {
            "pattern": ("US:{state}:{citation}" if is_us
                        else f"{jid}:{{instrument}}:{{id}}"),
            "enrich_fields": ["title", "publish_date", "official_url"],
        },
        "notes": "Batch 1（4B-2B）自动生成骨架；来源 scripts/gen_jurisdiction_contract.py",
    }
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jids", nargs="+")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    n = 0
    for jid in args.jids:
        pf = PROOFS / f"{jid}.json"
        if not pf.exists():
            print(f"⚠ {jid}: 缺 proof（先跑 onboard_jurisdiction_sources.py）")
            continue
        dest = CONTRACTS / f"{jid}.yaml"
        if dest.exists() and not args.overwrite:
            print(f"⏭ {jid}: contract 已存在（--overwrite 可覆盖）")
            continue
        proof = json.loads(pf.read_text(encoding="utf-8"))
        doc = build_contract(jid, proof)
        dest.write_text(
            "# ============================================================\n"
            f"# Jurisdiction Onboarding Contract —— {jid}"
            "（Batch 1 · 自动生成骨架）\n"
            "# 来源：scripts/gen_jurisdiction_contract.py（§5）；人工精修备注\n"
            "# ============================================================\n"
            + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        print(f"✅ {jid}: {dest.name}（{len(doc['official_channel_map'])} roles）")
        n += 1
    print(f"→ 生成 {n} 个 contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
