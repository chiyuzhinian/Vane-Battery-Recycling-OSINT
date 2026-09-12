# -*- coding: utf-8 -*-
"""对比 discover_eu_acts.py 的发现结果 vs 库内记录，找出缺口。

用法:
    py scripts/gap_check_discovered.py
    py scripts/gap_check_discovered.py --emit gaps.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# CELEX 模式: 3xxxxRxxxx, 5xxxxPCxxxx, 3xxxxLxxxx, 3xxxxDxxxx, 3xxxxXCxxxx, 3xxxxSCxxxx 等
CELEX_RE = re.compile(r"\b([35]\d{4}[A-Z]{1,2}\d{2,4}(?:R\(\d+\))?)\b")


def read_text_smart(path: Path) -> str:
    """自适应编码（PowerShell > 重定向产物可能是 UTF-16）。"""
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-16", errors="replace")


def parse_discovered(path: Path) -> list[dict]:
    """解析 _discover_acts.txt, 提取 (celex, date, title_hint, anchor)。"""
    items: list[dict] = []
    anchor = ""
    for raw in read_text_smart(path).splitlines():
        line = raw.strip()
        m_anchor = re.match(r"锚点\s+(\S+)\s+（(\S+)", line)
        if m_anchor:
            anchor = m_anchor.group(1)
            continue
        if line.startswith(("📜", "💡")):
            parts = line.split(None, 3)
            if len(parts) >= 3:
                celex = parts[1].strip()
                date = parts[2].strip()
                title = parts[3].strip() if len(parts) > 3 else ""
                items.append(
                    {"celex": celex, "date": date, "title": title, "anchor": anchor}
                )
    return items


def load_db_ids() -> dict[str, dict]:
    """扫描 outputs/*.jsonl, 建立 CELEX → 记录 的索引。"""
    index: dict[str, dict] = {}
    for fp in sorted(OUT.glob("*.jsonl")):
        if fp.name.startswith("_"):
            continue
        for line in fp.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            eid = rec.get("evidence_id") or ""
            url = rec.get("url") or ""
            # evidence_id 形如 eu_32025R0606；也从 URL 提取 CELEX
            celexes = set()
            m = re.search(r"eu_([35]\d{4}[A-Z]{1,2}\d{2,4}(?:R\(\d+\))?)$", eid)
            if m:
                celexes.add(m.group(1))
            m = re.search(r"CELEX[:%3A]+([35]\d{4}[A-Z]{1,2}\d{2,4})", url, re.I)
            if m:
                celexes.add(m.group(1).upper())
            for celex in celexes:
                index.setdefault(celex, rec)
    return index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(OUT / "_discover_acts.txt"))
    ap.add_argument("--emit", default="")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"❌ 未找到 {src}")
        return 1

    discovered = parse_discovered(src)
    db = load_db_ids()
    print(f"发现候选 {len(discovered)} 条；库内 CELEX 索引 {len(db)} 条\n")

    # 去重（跨锚点重复出现）
    seen: set[str] = set()
    gaps: list[dict] = []
    present: list[dict] = []
    for it in discovered:
        c = it["celex"]
        if c in seen:
            continue
        seen.add(c)
        if c in db:
            rec = db[c]
            it["db_status"] = rec.get("relevance") or rec.get("status") or "?"
            it["db_eid"] = rec.get("evidence_id", "")
            present.append(it)
        else:
            gaps.append(it)

    print(f"=== 缺口（未收录）: {len(gaps)} 条 ===")
    for it in sorted(gaps, key=lambda x: x["date"], reverse=True):
        marker = "📜" if it["celex"].startswith("3") else "💡"
        print(f"  {marker} {it['celex']:<18} {it['date']}  {it['title'][:85]}")
        print(f"       ↳ 锚点 {it['anchor']}")

    print(f"\n=== 已在库: {len(present)} 条（抽样 15）===")
    for it in sorted(present, key=lambda x: x["date"], reverse=True)[:15]:
        print(f"  ✓ {it['celex']:<18} [{it['db_status']}] {it['title'][:70]}")

    if args.emit:
        Path(args.emit).write_text(
            json.dumps({"gaps": gaps, "present": present}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n已写出 {args.emit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
