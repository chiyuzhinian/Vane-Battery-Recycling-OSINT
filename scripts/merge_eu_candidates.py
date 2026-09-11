"""把 discover_eu_acts.py 找到的候选，筛选固化进 `sources/eu-acts-tracked.yaml`。

为什么需要"筛选"这一步
----------------------
发现脚本给出 96 个候选，但**不能全收**：每个 CELEX 在采集时 = 1 次 SPARQL 查询，
96 个就是 30+ 分钟。所以按价值分级：

  ✅ 全收：sector 3（正式立法）—— 这些是权威文本，义务就写在里面
  ✅ 精选：sector 5 里**以 PC 开头**的提案（Proposal）——立法前 6~18 个月的预警信号
  ❌ 丢弃：SC（员工工作报告/影响评估）、AE（经社委员会意见）、DC（进度报告）
          —— 量大、程序性、对"义务是什么"帮助有限

输出是一个**纯数据文件**，`collect_eol_policies.build_plan` 直接读它。
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

SRC = ROOT / "sources" / "eu-acts-candidates.yaml"
DEST = ROOT / "sources" / "eu-acts-tracked.yaml"


def main() -> int:
    if not SRC.exists():
        print(f"缺少 {SRC}；先跑 py scripts/discover_eu_acts.py --emit {SRC}")
        return 2

    data = yaml.safe_load(SRC.read_text(encoding="utf-8")) or {}
    cands = data.get("candidates") or []
    print(f"候选 {len(cands)} 个")

    keep: list[dict] = []
    drop_kind: Counter = Counter()
    seen: set[str] = set()

    for c in cands:
        celex = (c.get("celex") or "").strip()
        if not celex or celex in seen:
            continue
        kind = c.get("kind") or ""
        # 5 位号里的类型码：PC=提案 SC=员工文件 AE=经社意见 DC=报告 AP=议会决议 AG=理事会立场
        m = re.match(r"^5\d{4}([A-Z]{2})", celex)
        code = m.group(1) if m else ""
        if kind == "立法":
            pass
        elif code == "PC":
            pass
        else:
            drop_kind[code or "?"] += 1
            continue
        seen.add(celex)
        keep.append({
            "celex": celex,
            "base": c.get("base") or "",
            "kind": kind,
            "date": c.get("date") or "",
            "title": (c.get("title") or "")[:170],
        })

    print(f"保留 {len(keep)} 个（丢弃 {sum(drop_kind.values())} 个：{dict(drop_kind)}）")
    by_kind = Counter(k["kind"] for k in keep)
    print(f"  立法 {by_kind.get('立法', 0)} · 提案 {by_kind.get('提案', 0)}")
    print()
    for k in keep:
        mark = "📜" if k["kind"] == "立法" else "💡"
        print(f"  {mark} {k['celex']:<18} {k['date']:<11} {k['title'][:78]}")

    DEST.write_text(
        "# 由 scripts/merge_eu_candidates.py 从 eu-acts-candidates.yaml 筛选生成\n"
        "# 来源：EUR-Lex SPARQL 按标题锚点发现（scripts/discover_eu_acts.py）\n"
        "#\n"
        "# ⚠️ 每个 CELEX 在采集时 = 1 次 SPARQL 查询，所以此表要**克制**：\n"
        "#    只保留「正式立法」与「PC 提案」；SC/AE/DC/AP/AG 等程序性文件已剔除。\n"
        "# ⚠️ 想重新生成：先 discover_eu_acts.py，再 merge_eu_candidates.py。\n"
        "\n"
        f"generated_from: eu-acts-candidates.yaml\n"
        f"tracked:\n"
        + "".join(
            f'  - celex: "{k["celex"]}"\n'
            f'    base: "{k["base"]}"\n'
            f'    kind: "{k["kind"]}"\n'
            f'    date: "{k["date"]}"\n'
            f'    title: "{k["title"].replace(chr(34), chr(39))}"\n'
            for k in keep
        ),
        encoding="utf-8",
    )
    print(f"\n→ 已写出 {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
