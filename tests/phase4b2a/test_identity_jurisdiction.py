# -*- coding: utf-8 -*-
"""Phase 4B-2A Step 6：管辖地记录身份 —— 官方编号构造与完整度。

纪律：identity 只从官方编号（meta.doc_key）构造；缺失即 None（不得猜）。
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.policy.identity_jurisdiction import (  # noqa: E402
    ISSUERS, identity_completeness, identity_from_meta,
)
from app.policy.jurisdiction_onboarding import list_contracts  # noqa: E402


def test_identity_from_doc_keys():
    se = identity_from_meta({"doc_key": "SE:SFS:2008:834", "language": "sv",
                             "source_role": "MS_LEGISLATION_DATABASE"})
    assert se["canonical_id"] == "SE:SFS:2008:834"
    assert se["jurisdiction"] == "SE" and se["official_identifier"] == "SFS:2008:834"
    assert "Regeringskansliet" in se["issuer"]
    pl = identity_from_meta({"doc_key": "PL:ISAP:WDU20090790666", "language": "pl"})
    assert pl["official_identifier"] == "ISAP:WDU20090790666"
    fi = identity_from_meta({"doc_key": "FI:SDK:2011/646", "language": "fi"})
    assert fi["jurisdiction"] == "FI"
    ca = identity_from_meta({"doc_key": "US-CA:PRC:42451", "language": "en"})
    assert ca["jurisdiction"] == "US-CA" and ca["official_identifier"] == "PRC:42451"
    wa = identity_from_meta({"doc_key": "US-WA:RCW:70A.555", "language": "en"})
    assert wa["jurisdiction"] == "US-WA"


def test_identity_missing_is_none():
    assert identity_from_meta({}) is None
    assert identity_from_meta(None) is None
    assert identity_from_meta({"doc_key": "ONLYONE"}) is None   # 无编号段


def test_issuers_cover_all_contracts():
    ids = set(list_contracts())
    assert ids, "需要存在 onboarding 契约"
    missing = ids - set(ISSUERS)
    assert not missing, f"ISSUERS 缺管辖地：{sorted(missing)}"


def test_identity_completeness_on_artifacts():
    for jid, pattern in (("SE", "jurisdiction_se_*.jsonl"),
                         ("US-CA", "jurisdiction_us-ca_*.jsonl"),
                         ("US-WA", "jurisdiction_us-wa_*.jsonl")):
        files = sorted(glob.glob(str(ROOT / "outputs" / pattern)))
        if not files:
            pytest.skip(f"需先运行采集：{jid}")
        rows = [json.loads(ln) for ln in
                Path(files[-1]).read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert all("identity" in r for r in rows), f"{jid} 记录缺 identity 字段"
        comp = identity_completeness(rows, jid)
        assert comp["total"] == len(rows)
        assert comp["pct"] == 100.0, f"{jid} 身份完整度异常：{comp}"
