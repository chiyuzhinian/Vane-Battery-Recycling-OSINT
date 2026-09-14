# -*- coding: utf-8 -*-
"""backfill_eu_placeholders.py —— Phase 4B-2B1 §4/§5（离线回填）。

把 sources/eurlex-fulltext/*.txt 与 outputs/eu_fulltext_*.jsonl 中的
正文合并回 outputs 里的 ``eu_{celex}`` 占位记录（**原地更新**——
load_records 先见者胜出，无法靠新增文件覆盖）。

纪律：
  · 幂等（text 已 ≥600 跳过；meta.backfilled_from 标记来源）
  · 不改 evidence_id / source_id / 顺序；只补 text + meta
  · 日志：outputs/audit/content_backfill_log.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

FULLTEXT_DIR = ROOT / "sources" / "eurlex-fulltext"
OUTPUTS = ROOT / "outputs"
LOG = OUTPUTS / "audit" / "content_backfill_log.json"
FULLTEXT_MIN = 600
TEXT_CAP = 400_000


def _parse_txt(fp: Path) -> tuple[str, str, str]:
    lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
    celex = fp.stem
    url = ""
    body_start = 0
    for i, ln in enumerate(lines[:6]):
        if ln.startswith("# CELEX"):
            celex = ln.replace("# CELEX", "").strip()
        elif ln.startswith("# http"):
            url = ln.replace("#", "").strip()
        elif not ln.startswith("#") and ln.strip():
            body_start = i
            break
    body = "\n".join(lines[body_start:]).strip()
    return celex, url, body


def collect_bodies() -> dict[str, dict]:
    """celex → {body, url, origin}（txt 优先；jsonl 补充）。"""
    out: dict[str, dict] = {}
    for fp in sorted(FULLTEXT_DIR.glob("*.txt")):
        celex, url, body = _parse_txt(fp)
        if len(body) >= FULLTEXT_MIN:
            out[celex] = {"body": body, "url": url,
                          "origin": f"sources/eurlex-fulltext/{fp.name}"}
    for fp in sorted(OUTPUTS.glob("eu_fulltext_*.jsonl")):
        for line in fp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            celex = str((r.get("meta") or {}).get("celex") or "")
            body = r.get("text") or ""
            if celex and len(body) >= FULLTEXT_MIN and celex not in out:
                out[celex] = {"body": body, "url": r.get("url") or "",
                              "origin": fp.name}
    return out


def main() -> int:
    bodies = collect_bodies()
    print(f"可用全文来源：{len(bodies)} 个 CELEX")
    updated: list[dict] = []
    scanned_files = 0
    for fp in sorted(OUTPUTS.glob("*.jsonl")):
        if fp.name.startswith(("_", "review", "policy_metadata")):
            continue
        lines = fp.read_text(encoding="utf-8", errors="replace").splitlines()
        changed = False
        new_lines: list[str] = []
        for line in lines:
            if not line.strip():
                new_lines.append(line)
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                new_lines.append(line)
                continue
            eid = str(r.get("evidence_id") or "")
            if not eid.startswith("eu_") or eid.startswith("eu_nim_") \
                    or eid.startswith("eu_fulltext_"):
                new_lines.append(line)
                continue
            meta = r.get("meta") or {}
            celex = str(meta.get("celex") or "")
            if eid.startswith("eu_eurlex_") or not celex:
                new_lines.append(line)
                continue
            src = bodies.get(celex)
            if not src:
                new_lines.append(line)
                continue
            if len(r.get("text") or "") >= FULLTEXT_MIN:
                new_lines.append(line)
                continue
            before = len(r.get("text") or "")
            r["text"] = src["body"][:TEXT_CAP]
            meta["content_state"] = "FULLTEXT"
            meta["backfilled_from"] = src["origin"]
            meta["full_chars"] = len(src["body"])
            if src["url"] and not r.get("url"):
                r["url"] = src["url"]
            r["meta"] = meta
            updated.append({"evidence_id": eid, "celex": celex,
                            "before": before, "after": len(r["text"]),
                            "origin": src["origin"], "file": fp.name})
            new_lines.append(json.dumps(r, ensure_ascii=False))
            changed = True
        if changed:
            fp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            scanned_files += 1

    log = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "EU 占位 ← 已有全文（原地合并；幂等）",
        "updated_count": len(updated),
        "updated": updated,
        "files_touched": scanned_files,
    }
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    for u in updated:
        print(f"  {u['evidence_id']:24s} {u['before']:>5d} -> {u['after']:>7d} "
              f"({u['origin']})")
    print(f"→ 更新 {len(updated)} 条；日志 {LOG.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
