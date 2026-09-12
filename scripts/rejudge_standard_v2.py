"""判定 2.0 全库重判 —— 把用户判例校准过的标准应用到所有通道。

与 `rejudge_us_standard.py` 的差别
----------------------------------
1. **覆盖全库**：EU（CELEX/关键词/成员国）+ US（FR）+ policy_* 文件
2. **分通道策略**（吸收历史教训）：
   · connector 类记录（eur_lex / us_federal / 各成员国官方通道）
     → 用 `judge_portal_policy`（判定 2.0：身份优先 + 处置链 + 对象边界 +
       授权法规路径）全量重判
   · browser_* 记录 → **只做对象边界过滤**（铅酸/消费类排除）。
     为什么不全量重判：`judge_browser` 处理过"站点导航噪声"（CalRecycle
     纺织/包装、ECHA 挑战页等），portal 判据没有那些防护 → 全量重判会
     把导航噪声重新引进来。
3. **人工审核优先**：已审核的记录跳过（判定不动；但也不做数据规范化——
   那件事归 clean_data_quality.py）

用法
----
    py scripts/rejudge_standard_v2.py            # 预览
    py scripts/rejudge_standard_v2.py --apply    # 落盘（自动备份 + prev_* 可回溯）
"""
from __future__ import annotations

import io
import re
import sys
import glob
import json
import shutil
import argparse
import collections
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT))

from app.core.relevance import (  # noqa: E402
    judge_portal_policy, V2_IN_SCOPE, V2_OFF_SCOPE)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

PATTERNS = ["eol_*.jsonl", "policy_EU_*.jsonl", "policy_US_*.jsonl"]
_V2_IN_RE = [re.compile(p, re.I) for p in V2_IN_SCOPE]
_V2_OFF_RE = [re.compile(p, re.I) for p in V2_OFF_SCOPE]


def load_decided() -> set[str]:
    p = OUT / "review_decisions.jsonl"
    ids: set[str] = set()
    if p.exists():
        for line in io.open(p, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("target_type") == "record" and d.get("target_id"):
                ids.add(d["target_id"])
    return ids


def is_browser(r: dict) -> bool:
    return (str(r.get("source_id") or "").startswith("browser_")
            or (r.get("meta") or {}).get("relevance_scenario") == "browser"
            or r.get("channel") == "browser_capture")


def off_scope(title: str) -> str | None:
    """对象边界：消费类/铅酸（无车用/储能/黑粉语境）→ 返回命中的排除锚点。"""
    if any(rx.search(title) for rx in _V2_IN_RE):
        return None
    for rx in _V2_OFF_RE:
        m = rx.search(title)
        if m:
            return m.group(0)[:24]
    return None


def new_verdict(r: dict) -> dict | None:
    """返回要写入的字段；None = 不改。"""
    title = r.get("title") or ""
    if is_browser(r):
        # browser 通道：只做对象边界过滤
        off = off_scope(title)
        if off and r.get("relevant"):
            return {"relevant": False, "needs_human_review": False,
                    "rejected_by": f"off_scope:{off}"}
        return None
    v = judge_portal_policy(r.get("text") or "", title)
    return {
        "relevant": bool(v.relevant),
        "relevance_score": round(float(v.score), 3),
        "hits": v.hits,
        "rejected_by": v.rejected_by,
        "needs_human_review": bool(v.needs_human_review),
        "review_reason": v.review_reason,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    decided = load_decided()
    files: list[Path] = []
    for pat in PATTERNS:
        files += [Path(p) for p in sorted(glob.glob(str(OUT / pat)))]

    per_file: dict[Path, list[dict]] = {}
    all_rows: list[dict] = []
    for fp in files:
        rows = []
        for line in io.open(fp, encoding="utf-8").read().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        per_file[fp] = rows
        all_rows += rows

    plans: dict[int, dict] = {}
    trans = collections.Counter()
    newly_out: list[dict] = []
    newly_in: list[dict] = []
    newly_review: list[dict] = []
    skipped = 0
    for r in all_rows:
        if (r.get("evidence_id") or "") in decided:
            skipped += 1
            continue
        nv = new_verdict(r)
        if nv is None:
            continue
        old = ("rel" if r.get("relevant") and not r.get("needs_human_review")
               else ("review" if r.get("relevant") else "irr"))
        new = ("rel" if nv["relevant"] and not nv["needs_human_review"]
               else ("review" if nv["relevant"] else "irr"))
        trans[f"{old} → {new}"] += 1
        plans[id(r)] = nv
        if old != "irr" and new == "irr":
            newly_out.append(r)
        elif old == "irr" and new == "rel":
            newly_in.append(r)
        elif old == "irr" and new == "review":
            newly_review.append(r)

    print(f"全库文件 {len(files)} 个；扫描行 {len(all_rows)}；"
          f"计划变更 {len(plans)} 条；跳过已审核 {skipped} 条\n")
    print("=" * 78)
    print("转移矩阵（旧 → 新）")
    print("=" * 78)
    for k, n in sorted(trans.items(), key=lambda kv: -kv[1]):
        print(f"  {k:20s} {n:5d}")

    print()
    print("=" * 78)
    print(f"新被排除 {len(newly_out)} 条 —— 抽样 30（检查是否误杀）")
    print("=" * 78)
    for r in newly_out[:30]:
        print(f"  · [{(r.get('source_id') or '?')[:20]:20s}] "
              f"{(r.get('title') or '')[:78]}")

    print()
    print("=" * 78)
    print(f"原排除 → 现相关 {len(newly_in)} 条 —— 全部（检查是否误收）")
    print("=" * 78)
    for r in newly_in[:30]:
        nv = plans[id(r)]
        print(f"  · {(r.get('title') or '')[:80]}")
        print(f"      hits={nv.get('hits', [])[:2]}")

    print()
    print(f"原排除 → 现待人工 {len(newly_review)} 条（抽样 12）")
    for r in newly_review[:12]:
        print(f"  · {(r.get('title') or '')[:80]}")

    if not args.apply:
        print("\n（预览模式，未写盘。加 --apply 落盘）")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = OUT / f"_backup_rejudge2_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for fp in files:
        shutil.copy2(fp, backup / fp.name)
    for fp in files:
        lines = []
        for r in per_file[fp]:
            nv = plans.get(id(r))
            if nv is not None:
                meta = r.get("meta") or {}
                if "prev_relevant" not in meta:
                    meta["prev_relevant"] = r.get("relevant")
                    meta["prev_score"] = r.get("relevance_score")
                    meta["prev_hits"] = r.get("hits")
                meta["rejudged_by"] = "portal_v2"
                r["meta"] = meta
                r.update(nv)
            lines.append(json.dumps(r, ensure_ascii=False))
        io.open(fp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"\n✅ 已写回 {len(files)} 个文件；备份于 {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
