"""全库数据质量审计 —— 找出"收录了但内容对不上"的各类脏记录（Phase 1）。

用户反馈（2026-09-12 原话）：
    「之前好多都是无关的」「不要收录一句就凭几个关键词命中，实际内容一点不符合」

本脚本把"脏"分成可操作的类别，每类给出**证据与处置建议**：

  A. 错误页/挑战页     —— "Page non trouvée" / 404 / Access Denied / Azure WAF …
  B. 机构首页/导航页    —— "XXX Home | XXX"、纯机构介绍（不是法规本体）
  C. 占位标题          —— "EU legislation CELEX X"（正文为空/占位，无法判断内容）
  D. 重复记录          —— 同一 evidence_id 或同一 CELEX 多条
  E. 空内容            —— text 极短（<120 字符），无可判定内容
  F. 非目标对象        —— 消费类电池 / 铅酸（按用户边界：只要 EV 动力+储能退役+黑粉）
  G. 程序性/个案       —— 特殊许可、申报表格、会议通知、拨款决定（非政策法规本体）

用法
----
    py scripts/audit_data_quality.py            # 只报告
    py scripts/audit_data_quality.py --dump     # 额外输出问题清单文件
"""
from __future__ import annotations

import io
import re
import sys
import glob
import json
import argparse
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

PATTERNS = ["eol_*.jsonl", "browser_*.jsonl", "policy_EU_*.jsonl", "policy_US_*.jsonl"]

# A. 错误页 / 挑战页
ERR_PAGE = re.compile(
    r"page non trouv|404|not found|access denied|azure waf|captcha|"
    r"enable javascript|just a moment|cloudflare|error|"
    r"页面不存在|找不到页面", re.I)

# B. 机构首页 / 导航页（标题里带 Home 或以机构名结尾的落地页）
HOME_PAGE = re.compile(r"\bhome\s*[|｜]|\|\s*\w+\s*$", re.I)

# C. 占位标题（CELEX 无标题记录）
PLACEHOLDER = re.compile(r"^EU legislation CELEX [0-9R()]+$", re.I)

# F. 明确非目标对象（用户边界外）——只在没有 EV/储能/黑粉语境时才成立
OFF_TARGET = re.compile(
    r"consumer (electronic|batter)|portable batter|button cell|hearing aid|"
    r"lead[- ]acid|铅酸|纽扣电池|助听器", re.I)
IN_SCOPE_CTX = re.compile(
    r"traction|electric vehicle|\bev\b|energy storage|industrial|"
    r"black mass|动力电池|储能|新能源汽车", re.I)


def load_all() -> list[dict]:
    seen: dict[str, dict] = {}
    for pat in PATTERNS:
        for fp in sorted(glob.glob(str(OUT / pat))):
            try:
                text = io.open(fp, encoding="utf-8").read()
            except (OSError, UnicodeDecodeError):
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (r.get("url") or r.get("evidence_id") or "").strip()
                if key and key not in seen:
                    seen[key] = r
    return list(seen.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", action="store_true")
    args = ap.parse_args()

    rows = load_all()
    rel = [r for r in rows if r.get("relevant")]
    print(f"全库去重 {len(rows)} 条；其中 relevant {len(rel)} 条")
    print("（以下问题统计**只在 relevant 内**，因为无关的不需要修）\n")

    buckets: dict[str, list[dict]] = collections.defaultdict(list)
    for r in rel:
        title = r.get("title") or ""
        text = r.get("text") or ""
        blob = f"{title}\n{text}"
        if ERR_PAGE.search(title) or ERR_PAGE.search(text[:200]):
            buckets["A.错误页/挑战页"].append(r)
        elif HOME_PAGE.search(title) and len(text) < 3000:
            buckets["B.机构首页/导航页"].append(r)
        if PLACEHOLDER.match(title.strip()):
            buckets["C.占位标题(无内容)"].append(r)
        if len(text.strip()) < 120:
            buckets["E.空内容(<120字符)"].append(r)
        if OFF_TARGET.search(blob) and not IN_SCOPE_CTX.search(blob):
            buckets["F.非目标对象(消费类/铅酸)"].append(r)

    # D. 重复（evidence_id 出现 >1 次的行 —— 注意上面已按 URL 去重，
    #    这里再按 evidence_id 统计"同 ID 多 URL"的重复）
    by_ev = collections.defaultdict(list)
    for r in rel:
        by_ev[r.get("evidence_id") or ""].append(r)
    dups = {k: v for k, v in by_ev.items() if len(v) > 1 and k}
    dup_rows = [x for v in dups.values() for x in v]
    buckets["D.同ID多URL重复"] = dup_rows

    print("=" * 80)
    for name in ("A.错误页/挑战页", "B.机构首页/导航页", "C.占位标题(无内容)",
                 "D.同ID多URL重复", "E.空内容(<120字符)", "F.非目标对象(消费类/铅酸)"):
        lst = buckets[name]
        print(f"{name:24s} {len(lst):4d} 条")
    print("=" * 80)

    for name in ("A.错误页/挑战页", "B.机构首页/导航页", "F.非目标对象(消费类/铅酸)"):
        lst = buckets[name]
        if not lst:
            continue
        print(f"\n▍{name} —— 样例 15：")
        for r in lst[:15]:
            print(f"  · [{(r.get('source_id') or '?')[:22]:22s}] "
                  f"{(r.get('title') or '')[:70]}")
            print(f"      url={(r.get('url') or '')[:88]}")

    if buckets["C.占位标题(无内容)"]:
        by_sid = collections.Counter(
            r.get("source_id") for r in buckets["C.占位标题(无内容)"])
        print(f"\n▍C.占位标题 —— 按来源：{dict(by_sid)}")
        print("   （这些记录标题只有 CELEX 号，正文为空/占位 —— 用户无法判断内容）")

    if dups:
        print(f"\n▍D.同ID多URL重复 —— {len(dups)} 组（共 {len(dup_rows)} 条）样例：")
        for k, v in list(dups.items())[:8]:
            print(f"  · {k} × {len(v)}")
            for x in v[:3]:
                print(f"      url={(x.get('url') or '')[:84]}")

    if args.dump:
        p = OUT / "_data_quality_issues.jsonl"
        with io.open(p, "w", encoding="utf-8") as f:
            for name, lst in buckets.items():
                for r in lst:
                    f.write(json.dumps({
                        "issue": name,
                        "evidence_id": r.get("evidence_id"),
                        "title": r.get("title"),
                        "url": r.get("url"),
                        "source_id": r.get("source_id"),
                    }, ensure_ascii=False) + "\n")
        print(f"\n问题清单已写出 {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
