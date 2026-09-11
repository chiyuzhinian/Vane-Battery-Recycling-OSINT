"""量化「合并正文快照」修复对欧盟层的影响。

背景：EUR-Lex 的 jsonl 记录只有 CELEX 号（raw_text 里只有占位符），
      相关性判定**没有内容可判** → 整部法规被静默丢弃。
      实测报废车指令 2000/53/EC（ELV 主干法）就是这样丢的。

本脚本按修复后的逻辑（`_with_fulltext` 并入已落盘正文）重新判定，
算出有多少条会从"不相关"翻成"相关"，并列出命中的黑粉监管线。
"""

from __future__ import annotations

import glob
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors.eur_lex import EurLexConnector  # noqa: E402
from app.core.relevance import black_mass_lines, judge_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

flip: list[tuple[str, str, float, list[str]]] = []
still = 0
already = 0
seen: set[str] = set()

for f in sorted(glob.glob(str(ROOT / "outputs" / "eol_EU_*.jsonl"))):
    for line in io.open(f, encoding="utf-8"):
        rec = json.loads(line)
        sid = rec.get("source_id") or ""
        if not sid.startswith("eu_eurlex"):
            continue
        celex = (rec.get("meta") or {}).get("celex")
        if not celex or celex in seen:
            continue
        seen.add(celex)
        if rec.get("relevant"):
            already += 1
            continue
        base = f"{rec.get('title') or ''}\n{rec.get('text') or ''}"
        merged = EurLexConnector._with_fulltext(celex, base)
        v = judge_policy(merged, rec.get("title") or "")
        if v.relevant:
            flip.append((celex, (rec.get("title") or "")[:66], v.score,
                         black_mass_lines(merged)))
        else:
            still += 1

print("=" * 78)
print("空壳修复对欧盟层的影响（按修复后逻辑重新判定）")
print("=" * 78)
print(f"  欧盟 CELEX 记录（去重后）：{already + len(flip) + still}")
print(f"    · 原本已相关      ：{already}")
print(f"    · 本次会翻转为相关：{len(flip)}  ← 此前被静默丢弃")
print(f"    · 仍不相关        ：{still}")
print()
for celex, title, score, lines in flip[:24]:
    mark = "／".join(lines) if lines else "—"
    print(f"  ✅ {celex:18} score={score} 线={mark}")
    print(f"       {title}")
