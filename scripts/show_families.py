"""查看文档家族（同一规则的不同阶段/后续文章）及各自判定 —— 排查家族传播。

用户要求：「后续相关的文章都要加进来进行一个**综合分析相关性**」
即：同一规则的提案 → 最终 → 更正 → 延期是**一个整体**，
不能因为某一篇标题模糊就把它排除。

本脚本按家族 key（规范化标题）分组，打印多成员家族的成员判定，
用于确认家族传播是否按预期工作。
"""
from __future__ import annotations

import io
import re
import sys
import glob
import json
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.relevance import judge_portal_policy as J  # noqa: E402
from scripts.rejudge_us_standard import _family_key  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def main() -> int:
    rows: list[dict] = []
    for fp in sorted(glob.glob(str(ROOT / "outputs" / "eol_US_*.jsonl"))):
        for line in io.open(fp, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    fam: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rows:
        fam[_family_key(r.get("title") or "")].append(r)

    multi = {k: v for k, v in fam.items() if len(v) >= 2}
    print(f"共 {len(fam)} 个家族，其中多成员 {len(multi)} 个\n")

    # 只显示**含相关/待人工成员**的家族 —— 那才是家族传播该起作用的地方
    interesting = []
    for key, members in multi.items():
        vs = [J(m.get("text") or "", m.get("title") or "") for m in members]
        if any(v.relevant for v in vs):
            interesting.append((key, members, vs))
    print(f"含相关/待人工成员的家族：{len(interesting)} 个\n")

    for key, members, vs in sorted(interesting, key=lambda t: -len(t[1]))[:12]:
        print("=" * 76)
        print(f"家族（{len(members)} 成员）：{key[:70]}")
        for m, v in zip(members, vs):
            mark = ("✅相关" if v.relevant and not v.needs_human_review
                    else ("🟡待人工" if v.relevant else "❌排除"))
            print(f"   {mark} [{(m.get('meta') or {}).get('type') or '?':14s}] "
                  f"{(m.get('title') or '')[:66]}")
            if v.hits:
                print(f"        hits={v.hits[:2]}")
        # 检查是否该传播（有强相关但仍有被排成员）
        strong = any(v.relevant and not v.needs_human_review
                     and v.score >= 0.75 for v in vs)
        dropped = sum(1 for v in vs if not v.relevant)
        if strong and dropped:
            print(f"   ⚠️ 该家族有强相关成员且有 {dropped} 条被排除 "
                  f"→ 应触发传播")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
