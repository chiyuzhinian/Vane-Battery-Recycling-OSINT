# -*- coding: utf-8 -*-
"""Jurisdiction Identity（Phase 4B-2A Step 6）—— 记录级官方身份。

口径（延续 Phase 4A §7 文档级身份）：
    每条新管辖地记录必须携带 identity：
        canonical_id / jurisdiction / official_identifier / issuer / language
        / source_role / official_domain
    canonical_id 来自 connector 写入的 meta.doc_key（官方编号体系）：
        SE:SFS:2008:834 ｜ PL:ISAP:WDU20090790666 ｜ FI:SDK:2011/646
        US-CA:AB:2021-2022:AB2440 ｜ US-CA:PRC:42451 ｜ US-WA:RCW:70A.555

纪律：identity 只从**官方编号/官方元数据**构造；缺失即 None（不得猜）。
"""
from __future__ import annotations

#: jurisdiction → 官方发布机关（展示与审计用）
ISSUERS: dict[str, str] = {
    "SE": "Regeringskansliet（Svensk författningssamling）",
    "PL": "Sejm RP（ISAP）",
    "FI": "Oikeusministeriö（Finlex）",
    "BE": "SPF Justice（eJustice / Moniteur belge）",
    "EE": "Riigi Teataja",
    "DE": "Bundesministerium der Justiz（gesetze-im-internet.de）",
    "NL": "KOOP（Basiswettenbestand）",
    "ES": "Agencia Estatal Boletín Oficial del Estado",
    "FR": "DILA（Légifrance / JORF）",
    "US": "U.S. Government（Federal Register / govinfo）",
    "US-CA": "California Legislature（leginfo）",
    "US-CO": "Colorado General Assembly",
    "US-GA": "Georgia General Assembly",
    "US-KY": "Kentucky Legislative Research Commission",
    "US-MN": "Minnesota Revisor of Statutes",
    "US-WA": "Washington State Legislature（RCW）",
}


def identity_from_meta(meta: dict | None) -> dict | None:
    """meta.doc_key → identity（缺失返回 None，组件齐全才完整）。"""
    meta = meta or {}
    doc_key = str(meta.get("doc_key") or "").strip()
    if not doc_key:
        return None
    parts = doc_key.split(":")
    if len(parts) < 2:
        return None
    jid = parts[0]
    return {
        "canonical_id": doc_key,
        "jurisdiction": jid,
        "official_identifier": ":".join(parts[1:]),
        "issuer": ISSUERS.get(jid, ""),
        "language": meta.get("language", ""),
        "source_role": meta.get("source_role", ""),
        "official_domain": meta.get("official_domain", ""),
    }


def identity_completeness(records: list[dict], jid: str = "") -> dict:
    """管辖地切片内的身份完整度（canonical_id + official_identifier + language）。"""
    rows = [r for r in records
            if not jid or (r.get("meta") or {}).get("jurisdiction") == jid]
    full = 0
    for r in rows:
        ident = r.get("identity") or identity_from_meta(r.get("meta"))
        if ident and ident.get("canonical_id") and ident.get("official_identifier") \
                and ident.get("language"):
            full += 1
    return {"total": len(rows), "with_identity": full,
            "pct": round(100.0 * full / len(rows), 1) if rows else 0.0}
