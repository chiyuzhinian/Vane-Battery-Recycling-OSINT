# -*- coding: utf-8 -*-
"""backfill_eu_online.py —— EU 占位在线回填（Phase 4B-2B1 §5，P0 主体）。

读 outputs/audit/content_completeness.json 的 EU P0 缺口 → 经 eur_lex
connector fetch_fulltext 逐条抓取 → 落盘 sources/eurlex-fulltext/*.txt →
原地合并到 outputs 记录。

失败处理（不掩盖）：
  · EUR-Lex 202/站点降级 → meta.content_state="FETCH_FAILED" + failure_reason
  · 成功但 <600 字符（更正件类短文书）→ meta.short_instrument=True
重试：--rounds N（默认 2），每轮间隔 --sleep 秒（默认 20）。

用法：py scripts/backfill_eu_online.py [--rounds 2] [--sleep 20]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

FULLTEXT_DIR = ROOT / "sources" / "eurlex-fulltext"
OUTPUTS = ROOT / "outputs"
TEXT_CAP = 400_000


def _eu_gap_list() -> list[str]:
    fp = OUTPUTS / "audit" / "content_completeness.json"
    d = json.loads(fp.read_text(encoding="utf-8"))
    out = []
    for x in d["backfill_queue"]:
        if x["backfill_status"] != "P0":
            continue
        eid = x["evidence_id"]
        if not eid.startswith("eu_") or eid.startswith(
                ("eu_nim_", "eu_fulltext_", "eu_eurlex_", "eu_cellar_")):
            continue
        celex = eid[len("eu_"):]
        out.append(celex)
    return sorted(set(out))


def _merge_bodies(bodies: dict[str, tuple[str, bool]]) -> int:
    """celex → (body, short) 原地合并。返回更新条数。"""
    updated = 0
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review")):
            continue
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        changed = False
        out = []
        for line in lines:
            if not line.strip():
                out.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            eid = str(rec.get("evidence_id") or "")
            if not eid.startswith("eu_") or eid.startswith(
                    ("eu_nim_", "eu_fulltext_", "eu_eurlex_")):
                out.append(line)
                continue
            celex = eid[len("eu_"):]
            hit = bodies.get(celex)
            if not hit:
                out.append(line)
                continue
            body, short = hit
            if len(rec.get("text") or "") >= 600:
                out.append(line)
                continue
            rec["text"] = body[:TEXT_CAP]
            meta = rec.get("meta") or {}
            meta["content_state"] = "FULLTEXT"
            meta["backfilled_from"] = "eur-lex online fetch"
            meta["full_chars"] = len(body)
            if short:
                meta["short_instrument"] = True
            rec["meta"] = meta
            out.append(json.dumps(rec, ensure_ascii=False))
            changed = True
            updated += 1
        if changed:
            fp.write_text("\n".join(out) + "\n", encoding="utf-8")
    return updated


def _mark_failed(celex: str, reason: str) -> int:
    marked = 0
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review")):
            continue
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        changed = False
        out = []
        for line in lines:
            if not line.strip():
                out.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                out.append(line)
                continue
            if rec.get("evidence_id") == f"eu_{celex}" and \
                    len(rec.get("text") or "") < 600:
                meta = rec.get("meta") or {}
                meta["content_state"] = "FETCH_FAILED"
                meta["failure_reason"] = reason
                rec["meta"] = meta
                out.append(json.dumps(rec, ensure_ascii=False))
                changed = True
                marked += 1
            else:
                out.append(line)
        if changed:
            fp.write_text("\n".join(out) + "\n", encoding="utf-8")
    return marked


async def _run(rounds: int, sleep_s: int) -> int:
    from app.connectors import get_connector
    targets = _eu_gap_list()
    print(f"EU 在线回填目标：{len(targets)} 条")
    remaining = list(targets)
    ok_bodies: dict[str, tuple[str, bool]] = {}
    failures: dict[str, str] = {}
    for rnd in range(1, rounds + 1):
        if not remaining:
            break
        print(f"\n=== Round {rnd}/{rounds}（{len(remaining)} 条）===")
        async with get_connector("eur_lex") as conn:
            for celex in list(remaining):
                try:
                    text, _ = await conn.fetch_fulltext(celex)
                except Exception as exc:  # noqa: BLE001
                    failures[celex] = type(exc).__name__
                    print(f"  ❌ {celex:<20} {type(exc).__name__}")
                    continue
                if not text or len(text) < 150:
                    failures[celex] = f"too_short({len(text or '')})"
                    print(f"  ⚠️ {celex:<20} 过短 {len(text or '')}")
                    continue
                short = len(text) < 600
                ok_bodies[celex] = (text, short)
                # 落盘快照
                FULLTEXT_DIR.mkdir(parents=True, exist_ok=True)
                (FULLTEXT_DIR / f"{celex}.txt").write_text(
                    f"# CELEX {celex}\n# https://eur-lex.europa.eu/"
                    f"legal-content/EN/TXT/?uri=CELEX:{celex}\n"
                    f"# 抓取 {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
                    f"（正文 {len(text)} 字符）\n\n{text}",
                    encoding="utf-8")
                remaining.remove(celex)
                print(f"  ✅ {celex:<20} {len(text):>7d} 字符"
                      f"{'（短文书）' if short else ''}")

    upd = _merge_bodies(ok_bodies) if ok_bodies else 0
    print(f"\n合并更新 {upd} 条")
    # 全轮失败者 → FETCH_FAILED（reason 汇总）
    why = {}
    for celex in remaining:
        why[celex] = failures.get(celex, "unknown")
    for celex, reason in list(why.items())[:80]:
        _mark_failed(celex, f"eur-lex fetch failed: {reason}")
    if why:
        from collections import Counter
        print("失败归类：", dict(Counter(why.values())))
    return upd


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--sleep", type=int, default=20)
    args = ap.parse_args()
    updated = asyncio.run(_run(args.rounds, args.sleep))
    print(f"→ 完成（更新 {updated}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
