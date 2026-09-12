"""数据质量清洗 —— 把"收录了但内容对不上"的脏记录收拾干净（Phase 1）。

审计（`scripts/audit_data_quality.py`）发现的四类可自动处置的问题：

  A. 错误页（"Page non trouvée" 等）      → 标 irrelevant（rejected_by=dead_page）
  C. 占位标题（"EU legislation CELEX X"） → **回填真标题**（从同 CELEX 的记录取）
  D. 同 ID 多 URL 重复                    → 保留"有真标题"的一条，其余标 duplicate
  E. 空内容（<120 字符）                  → 标 needs_human_review（不武断删）

原则（延续项目既有约束）
------------------------
· **不删除任何记录** —— 只改判定字段 + 写 `meta.*` 说明；可回溯、可回滚
· **先备份** 原文件到 `outputs/_backup_clean_<stamp>/`
· **首次才写 prev_***（重复运行不覆盖最早的原值）
· 已人工审核的记录**跳过**

用法
----
    py scripts/clean_data_quality.py            # 预览
    py scripts/clean_data_quality.py --apply    # 落盘
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

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

PATTERNS = ["eol_*.jsonl", "browser_*.jsonl", "policy_EU_*.jsonl", "policy_US_*.jsonl"]

# A. 错误页 —— 只保留高置信标记。
#   ⚠️ 不要用裸 `404`："Clean Water Act **Section 404**" 会被误伤（实测）
#   也不要裸 `error`（会卷进 terrorism 之类）。
DEAD_PAGE = re.compile(
    r"page non trouv|\b404\s*(not found|error)\b|\bnot found\b"
    r"|access denied|azure waf|enable javascript|just a moment"
    r"|页面不存在|找不到页面", re.I)

# C. 占位标题
PLACEHOLDER = re.compile(r"^EU legislation CELEX ([0-9R()]+)$", re.I)

# 英文法规标题特征（回填时优先选英文版，避免拿到匈牙利语/德语等其他语言版本）
EN_TITLE = re.compile(
    r"\b(regulation|directive|decision|corrigendum|amending|supplementing|"
    r"implementing|delegated)\b", re.I)
# corrigendum 后缀：32023R1542R(01) → base=32023R1542, suf=R(01)
CORRIG = re.compile(r"^([0-9]{4}[A-Z]?[0-9]+)(R\(\d+\))$")


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

    # ---- C 类：建"真标题"索引（evidence_id → 最佳标题）----
    best_title: dict[str, str] = {}
    for r in all_rows:
        ev = r.get("evidence_id") or ""
        t = (r.get("title") or "").strip()
        if ev and t and not PLACEHOLDER.match(t):
            # 排序键：**英文优先** > 更长（信息更全）
            # ⚠️ 实测：corrigendum 的记录里混着匈牙利语/德语/芬兰语标题，
            #    按长度选会回填出外语标题（用户看不懂、也无法搜索）
            score = (1 if EN_TITLE.search(t) else 0, len(t))
            cur = best_title.get(ev)
            if cur is None:
                best_title[ev] = t
            else:
                cur_score = (1 if EN_TITLE.search(cur) else 0, len(cur))
                if score > cur_score:
                    best_title[ev] = t

    # 构造回填：corrigendum 无英文标题时，用本体英文标题拼标准格式
    #   例：32024R1252R(01) → "Corrigendum to Regulation (EU) 2024/1252 [R(01)]"
    def synth_title(ev: str) -> str:
        celex = ev[3:] if ev.startswith("eu_") else ev
        m = CORRIG.match(celex)
        if not m:
            return ""
        base_ev = f"eu_{m.group(1)}"
        base = best_title.get(base_ev, "")
        if not base:
            return ""
        # 本体标题里已含 "Regulation (EU) 2023/1542"，直接拼 Corrigendum to
        return f"Corrigendum to {base.split(' of ')[0]} [{m.group(2)}]"

    # ---- D 类：同 evidence_id 多条 → **只用于定位"占位版 vs 真标题版"**，
    #      不做批量重复标记（跨文件的同 ID 行是采集批次的自然重叠，
    #      读取时由 store.py 的 URL 去重处理；在这里标 irrelevant 反而危险）。
    best_url: dict[str, str] = {}      # evidence_id → 真标题版的 URL
    for r in all_rows:
        ev = r.get("evidence_id") or ""
        t = (r.get("title") or "").strip()
        u = (r.get("url") or "").strip()
        if ev and t and not PLACEHOLDER.match(t) and u:
            best_url.setdefault(ev, u)

    plans: dict[int, dict] = {}        # id(row) → 变更计划
    stats = collections.Counter()

    for r in all_rows:
        ev = r.get("evidence_id") or ""
        if ev in decided:
            continue
        title = (r.get("title") or "").strip()
        text = r.get("text") or ""
        change: dict = {}

        # A. 错误页
        if DEAD_PAGE.search(title) or DEAD_PAGE.search(text[:200]):
            change["relevant"] = False
            change["needs_human_review"] = False
            change["rejected_by"] = "dead_page"
            stats["A.错误页"] += 1
            plans[id(r)] = change
            continue

        # C. 占位标题 → 回填标题 + **URL 归一化**（eurlex 可读链）
        m = PLACEHOLDER.match(title)
        if m:
            celex = m.group(1)
            # ⚠️ 只接受**含英文特征**的候选标题：
            #   实测有的 evidence_id 只存了外语标题（匈牙利语/德语/芬兰语），
            #   若不加这层过滤，会回填出用户看不懂、无法检索的外语标题。
            real = ""
            for cand in (best_title.get(ev), best_title.get(f"eu_{celex}")):
                if cand and EN_TITLE.search(cand):
                    real = cand
                    break
            if not real:
                real = synth_title(ev) or synth_title(f"eu_{celex}")
            real_url = best_url.get(ev) or best_url.get(f"eu_{celex}")
            if real:
                change["_title"] = real
                if real_url:
                    change["_url"] = real_url
                stats["C.标题回填"] += 1
                if real_url:
                    stats["C.URL 归一化"] += 1
            else:
                # 无英文标题可回填 —— 再分两种（用户原则：**内容相符合**）：
                #   · 有实质正文 → 待人工补标题（值得救）
                #   · 正文也是占位模板 → **排除**（没内容的记录不该占着"相关"位）
                body = text.strip()
                is_placeholder_body = ("EU legislation CELEX" in body[:80]
                                       or len(body) < 300)
                if is_placeholder_body:
                    change["relevant"] = False
                    change["needs_human_review"] = False
                    change["rejected_by"] = "placeholder_no_content"
                    stats["C.占位且无内容→排除"] += 1
                else:
                    change["needs_human_review"] = True
                    change["review_reason"] = ("标题缺失（仅 CELEX 号）但正文有实质内容，"
                                               "需人工补标题后复核")
                    stats["C.有正文缺标题→待人工"] += 1
            plans[id(r)] = change
            continue

        # E. 空内容 → 待人工
        if len(text.strip()) < 120 and r.get("relevant") and not r.get("needs_human_review"):
            change["needs_human_review"] = True
            change["review_reason"] = "正文极短（<120 字符），无法据内容判断相关性"
            stats["E.空内容→待人工"] += 1
            plans[id(r)] = change

    print("清洗计划：")
    for k, v in stats.most_common():
        print(f"  {k:22s} {v:4d}")
    print(f"  合计变更 {len(plans)} 条")

    # 样例
    for label, key in (("A.错误页", "A.错误页"), ("C.标题回填", "C.标题回填")):
        if not stats[key]:
            continue
        print(f"\n▍{label} 样例：")
        n = 0
        for r in all_rows:
            c = plans.get(id(r))
            if not c:
                continue
            if key == "A.错误页" and c.get("rejected_by") != "dead_page":
                continue
            if key == "C.标题回填" and "_title" not in c:
                continue
            print(f"  · {(r.get('title') or '')[:64]}")
            if "_title" in c:
                print(f"      → 回填为：{c['_title'][:76]}")
            n += 1
            if n >= 6:
                break

    if not args.apply:
        print("\n（预览模式，未写盘。加 --apply 落盘）")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = OUT / f"_backup_clean_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for fp in files:
        shutil.copy2(fp, backup / fp.name)

    for fp in files:
        lines = []
        for r in per_file[fp]:
            c = plans.get(id(r))
            if c:
                meta = r.get("meta") or {}
                if "prev_relevant" not in meta:
                    meta["prev_relevant"] = r.get("relevant")
                    meta["prev_needs_human_review"] = r.get("needs_human_review")
                    meta["prev_title"] = r.get("title")
                if "_dup_of" in c:
                    meta["duplicate_of"] = c.pop("_dup_of")
                if "_title" in c:
                    meta["title_backfilled_from"] = "same_evidence_id"
                    r["title"] = c.pop("_title")
                if "_url" in c:
                    meta["url_normalized_from"] = r.get("url")
                    r["url"] = c.pop("_url")
                meta["cleaned_by"] = "clean_data_quality_v1"
                r["meta"] = meta
                r.update(c)
            lines.append(json.dumps(r, ensure_ascii=False))
        io.open(fp, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"\n✅ 已写回 {len(files)} 个文件；备份于 {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
