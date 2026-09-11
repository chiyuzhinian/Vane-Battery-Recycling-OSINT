"""按用户标准重判美国记录 —— 「报废退役电池处置」口径 + 家族综合判定。

用户的指令链（2026-09-12）
-------------------------
  1. 「我需要的是**报废退役电池处置**相关的政策法规，黑粉也有」
  2. 「这个是符合标准的 —— 按照这个纠正」   ※指 PHMSA 安全通告
  3. 「后续相关的文章都要加进来进行一个**综合分析相关性**」

据此本脚本做两件事：
  A. **单篇重判**：改用 `judge_portal_policy`（身份优先 + 处置链 + 财政框架剔除）
     —— 判据与标准样本测试在 `tests/test_portal_judge.py`
  B. **家族综合判定**：同一规则的文档序列（提案 → 最终 → 更正 → 延期）
     是一个整体，不能拆散：
       · 家族 key = 规范化标题（去阶段词/标点）
       · 家族内只要有一篇达到「强相关」，其余原本被排除的成员**提升为待人工**
         （不直接判相关 —— 后续文章可能只是程序性通知，交人工裁）
     这正对应「后续相关的文章都要加进来进行一个综合分析相关性」。

安全设计
--------
  · 默认**只预览**，不写盘；`--apply` 才原地更新，且：
      - 先把原文件备份到 `outputs/_backup_rejudge_<stamp>/`
      - 每条记录把旧判定存进 `meta.prev_relevant / prev_score / prev_hits`
        —— 可回溯、可回滚（符合"不能静默丢失"）
  · **已经人工审核过的记录**（存在于 review_decisions.jsonl）不参与重判：
    人工判定优先，机器不得覆盖（面板本来就是这么叠加的）。

用法
----
    py scripts/rejudge_us_standard.py                  # 预览
    py scripts/rejudge_us_standard.py --apply          # 落盘
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

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"
sys.path.insert(0, str(ROOT))

from app.core.relevance import judge_portal_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

TARGET_FILES = ("eol_US_*.jsonl",)

# 规范化标题时抹掉的"阶段词"（同一规则的不同阶段共享家族）
_STAGE_WORDS = re.compile(
    r"\b(proposed|final|correcting|correction|extension|delay|reopening|"
    r"withdrawal|notice of|amendment)\b", re.I)


def _family_key(title: str) -> str:
    """标题 → 家族 key（同一规则序列的文档归为一族）。

    ⚠️ 只做轻量规范化：小写、去标点、去阶段词、取前 90 字符。
       不做语义聚类 —— 过度归并会把不相关的文档拉进同一族。
    """
    t = (title or "").lower()
    t = _STAGE_WORDS.sub(" ", t)
    t = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:90]


def _load_decided_ids() -> set[str]:
    """已被人工审核的 record id —— 这些不参与机器重判。"""
    p = OUT / "review_decisions.jsonl"
    ids: set[str] = set()
    if not p.exists():
        return ids
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


def _new_verdict(r: dict) -> dict:
    """对一条记录跑新判据，返回将要写入的字段。"""
    v = judge_portal_policy(r.get("text") or "", r.get("title") or "")
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
    ap.add_argument("--apply", action="store_true",
                    help="把重判结果写回 jsonl（默认只预览）")
    args = ap.parse_args()

    decided = _load_decided_ids()
    files: list[Path] = []
    for pat in TARGET_FILES:
        files += [Path(p) for p in sorted(glob.glob(str(OUT / pat)))]
    if not files:
        print("没有找到 US 记录文件")
        return 1

    print(f"目标文件 {len(files)} 个；已人工审核 {len(decided)} 条（跳过重判）\n")

    # ---- 第一遍：载入 + 单篇重判 ----
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

    new_map: dict[int, dict] = {}          # id(row) → 新判定
    skipped = 0
    for r in all_rows:
        if (r.get("evidence_id") or "") in decided:
            skipped += 1
            continue
        new_map[id(r)] = _new_verdict(r)

    # ---- 第二遍：家族聚合 ----
    fam: dict[str, list[dict]] = collections.defaultdict(list)
    for r in all_rows:
        if id(r) in new_map:
            fam[_family_key(r.get("title") or "")].append(r)

    promoted = 0
    fam_sizes = collections.Counter()
    for key, members in fam.items():
        if len(members) < 2:
            continue
        fam_sizes[len(members)] += 1
        strong = any(
            new_map[id(m)]["relevant"]
            and not new_map[id(m)]["needs_human_review"]
            and new_map[id(m)]["relevance_score"] >= 0.75
            for m in members
        )
        if not strong:
            continue
        for m in members:
            nv = new_map[id(m)]
            if not nv["relevant"]:
                # 家族里有强相关成员 → 本成员"血亲"提升为待人工（不直接判相关）
                nv["relevant"] = True
                nv["needs_human_review"] = True
                nv["relevance_score"] = max(nv["relevance_score"], 0.45)
                nv["review_reason"] = ("与本主题的强相关文档同族（同一规则的"
                                       "不同阶段/后续文章），需人工确认")
                nv["hits"] = list(nv["hits"]) + ["family:promoted"]
                promoted += 1

    # ---- 统计 ----
    trans = collections.Counter()
    newly_out: list[dict] = []
    newly_review: list[dict] = []
    for r in all_rows:
        if id(r) not in new_map:
            continue
        old = "rel" if r.get("relevant") else "irr"
        old += "+h" if r.get("needs_human_review") else ""
        nv = new_map[id(r)]
        new = "rel" if nv["relevant"] and not nv["needs_human_review"] else (
            "review" if nv["relevant"] else "irr")
        trans[f"{old} → {new}"] += 1
        if old.startswith("rel") and new == "irr":
            newly_out.append(r)
        elif old == "irr" and new == "review":
            newly_review.append(r)

    print("=" * 78)
    print("重判转移矩阵（旧判定 → 新判定；+h = 旧判定为待人工）")
    print("=" * 78)
    for k, n in sorted(trans.items(), key=lambda kv: -kv[1]):
        print(f"  {k:22s} {n:5d}")
    print(f"\n家族传播：{promoted} 条被同族强相关文档提升为待人工"
          f"（涉及 {sum(1 for s, c in fam_sizes.items() if s >= 2)} 个多成员家族）"
          f"；跳过重判 {skipped} 条（已人工审核）")

    print()
    print("=" * 78)
    print(f"新被排除（原判相关 → 现排除）{len(newly_out)} 条 —— 抽样 30")
    print("=" * 78)
    for r in newly_out[:30]:
        print(f"  · [{(r.get('meta') or {}).get('type') or '?':14s}] "
              f"{(r.get('title') or '')[:96]}")
    if len(newly_out) > 30:
        print(f"  … 另有 {len(newly_out) - 30} 条（完整清单见 --apply 后的报告）")

    # ---- 透查 ①：旧"待人工"里被直接排掉的（最需要防误杀的一类）----
    print()
    print("=" * 78)
    print("透查① 原判「待人工」→ 现「排除」—— 抽样 40（检查是否误杀）")
    print("=" * 78)
    warn_out = [r for r in all_rows
                if id(r) in new_map and r.get("relevant")
                and r.get("needs_human_review")
                and not new_map[id(r)]["relevant"]]
    for r in warn_out[:40]:
        print(f"  · [{(r.get('meta') or {}).get('type') or '?':14s}] "
              f"{(r.get('title') or '')[:92]}")
    if len(warn_out) > 40:
        print(f"  … 另有 {len(warn_out) - 40} 条")
    # 旧待人工的来源分类（用旧 hits 判断，容易发现"整类被排"）
    src = collections.Counter()
    for r in warn_out:
        h = " ".join(r.get("hits") or [])
        src["maybe(税优/材料/制造)" if "maybe:" in h else
            ("line(黑粉四线)" if "line:" in h else
             ("ctx(上下文词)" if "ctx:" in h else "其他"))] += 1
    print(f"  旧命中来源分布：{dict(src)}")

    # ---- 透查 ②：原被排除、现变自动相关的 ----
    print()
    print("=" * 78)
    print("透查② 原「排除」→ 现「相关」（之前可能漏收的）")
    print("=" * 78)
    gained = [r for r in all_rows
              if id(r) in new_map and not r.get("relevant")
              and new_map[id(r)]["relevant"]
              and not new_map[id(r)]["needs_human_review"]]
    for r in gained[:20]:
        nv = new_map[id(r)]
        print(f"  · {(r.get('title') or '')[:80]}")
        print(f"      hits={nv['hits'][:3]}")
    if not gained:
        print("  （无）")

    if args.apply:
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = OUT / f"_backup_rejudge_{stamp}"
        backup.mkdir(parents=True, exist_ok=True)
        for fp in files:
            shutil.copy2(fp, backup / fp.name)
        for fp in files:
            lines = []
            for r in per_file[fp]:
                nv = new_map.get(id(r))
                if nv is None:
                    lines.append(json.dumps(r, ensure_ascii=False))
                    continue
                meta = r.get("meta") or {}
                # ⚠️ 只在**首次**重判时记录原值 —— 重复 apply 不得覆盖，
                #    否则第一次的原始判定就找不回来了（可回溯性会被破坏）。
                if "prev_relevant" not in meta:
                    meta["prev_relevant"] = r.get("relevant")
                    meta["prev_score"] = r.get("relevance_score")
                    meta["prev_hits"] = r.get("hits")
                meta["rejudged_by"] = "portal_v1"
                r["meta"] = meta
                r.update(nv)
                lines.append(json.dumps(r, ensure_ascii=False))
            io.open(fp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print(f"\n✅ 已写回 {len(files)} 个文件；原文件备份于 {backup}")
    else:
        print("\n（预览模式：未写盘。加 --apply 落盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
