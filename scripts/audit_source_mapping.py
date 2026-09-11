"""审计 `source_id → 国家` 映射的完整性，并预览地图聚合结果。

为什么要单独审计
----------------
UI 世界地图靠 `source_id` 反推国家归属（见 `app/core/geo.py`）。
**漏映射的后果是「静默丢失」**：某个源没登记 → 它的数据从地图上消失，
不报错、不告警 —— 属于最难发现的一类缺陷。

所以：**新增源之后必须跑一次**。

用法
----
    py scripts/audit_source_mapping.py              # 完整审计 + 地图聚合预览
    py scripts/audit_source_mapping.py --quiet      # 只报问题（退出码非 0 表示有未映射源）
"""
from __future__ import annotations

import glob
import io
import json
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from app.core.geo import (  # noqa: E402
    SOURCE_COUNTRY,
    country_of,
    known_units,
    rollup_parent,
    unit_of,
    unmapped_sources,
)

# 与 scripts/make_report.py 的 load_records() **同口径**：
# 文件按名字排序（= 时间序）+ 按 URL 去重 + 先出现者胜出。
# 口径不一致会导致本脚本的数字与 policy-report 对不上。
PATTERNS = ("outputs/eol_*.jsonl", "outputs/browser_*.jsonl",
            "outputs/policy_EU_*.jsonl", "outputs/policy_US_*.jsonl")


def load() -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    files: list[str] = []
    for p in PATTERNS:
        files += sorted(glob.glob(p))
    for fp in files:
        try:
            fh = io.open(fp, encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (r.get("url") or r.get("evidence_id") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(r)
        fh.close()
    return out


def main() -> int:
    quiet = "--quiet" in sys.argv
    records = load()
    if not records:
        print("⚠️ 没有读到任何记录（outputs/*.jsonl 为空？）")
        return 2

    # ---- 按 source_id 聚合 ----
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "relevant": 0})
    for r in records:
        sid = (r.get("source_id") or "?").strip()
        by_source[sid]["total"] += 1
        if r.get("relevant"):
            by_source[sid]["relevant"] += 1

    # ---- 未映射检查（核心）----
    bad = unmapped_sources(by_source.keys())
    if bad:
        print("=" * 74)
        print(f"❌ 有 {len(bad)} 个 source_id **未登记国家归属** —— 这些数据不会出现在地图上")
        print("=" * 74)
        for s in bad:
            print(f"   {by_source[s]['total']:>5} 条  {s}")
        print("\n   → 请在 app/core/geo.py 的 SOURCE_COUNTRY 中登记\n")
    elif not quiet:
        print(f"✅ 国家映射覆盖完整：{len(by_source)}/{len(by_source)} 个 source_id 均已登记\n")

    if quiet:
        return 1 if bad else 0

    # ---- 按地理单元聚合（州级并入父国家）----
    by_geo: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "relevant": 0, "sources": 0})
    src_per_geo: dict[str, set] = defaultdict(set)
    for sid, st in by_source.items():
        code = rollup_parent(country_of(sid))
        by_geo[code]["total"] += st["total"]
        by_geo[code]["relevant"] += st["relevant"]
        src_per_geo[code].add(sid)
    for code, st in by_geo.items():
        st["sources"] = len(src_per_geo[code])

    print("=" * 74)
    print("地图聚合预览（州级已并入父国家；这是 /api/map 将要返回的口径）")
    print("=" * 74)
    print(f"{'代码':<7}{'名称':<14}{'条数':>6}{'相关':>6}{'源数':>5}{'相关率':>8}")
    print("-" * 74)
    for code in sorted(by_geo, key=lambda c: -by_geo[c]["total"]):
        st = by_geo[code]
        rate = st["relevant"] / st["total"] * 100 if st["total"] else 0
        print(f"{code:<7}{unit_of(code).name_zh:<14}{st['total']:>6}"
              f"{st['relevant']:>6}{st['sources']:>5}{rate:>7.0f}%")
    print("-" * 74)
    tot = sum(s["total"] for s in by_geo.values())
    rel = sum(s["relevant"] for s in by_geo.values())
    print(f"{'合计':<21}{tot:>6}{rel:>6}{'':>5}{rel / tot * 100:>7.0f}%")

    # ---- 州级明细单独列出（并入父国家后仍要能追溯）----
    states = [c for c in by_geo if unit_of(c).level == "state"]
    if states:
        print("\n州级明细（在地图上并入父国家，但钻取时单独展示）：")
        for c in states:
            st = by_geo[c]
            print(f"   {c:<7}{unit_of(c).name_zh:<20}{st['total']:>5} 条 / 相关 {st['relevant']}")

    print(f"\n已登记地理单元：{len(known_units())} 个"
          f"（{', '.join(u.code for u in known_units())}）")

    # ---- 未映射的源（若有）也在这里列出，避免只检查不报告 ----
    if bad:
        print(f"\n⚠️ 注意：上表不含 {len(bad)} 个未登记源的数据（共 "
              f"{sum(by_source[s]['total'] for s in bad)} 条）")

    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
