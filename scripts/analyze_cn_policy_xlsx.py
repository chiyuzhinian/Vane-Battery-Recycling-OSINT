"""读取《中国电池回收政策法规标准》Excel —— 把用户认可的"合格形态"读全。

用途（Phase 0 校准）
--------------------
这份中国清单是用户心中的**正样本全集**：
  「参考这些去设置整个搜证体系」
  「最终我需要的是**内容相符合**，而不是收录一句就凭几个关键词命中」

读它不是为了照抄，而是为了提取**标尺**：
  ① 类型结构：法律 / 行政法规 / 部门规章 / 国标 / 行标 / 规范性文件 各占多少
  ② 标题措辞：词频（"综合利用""梯次利用""规范条件""溯源"…）
  ③ 字段结构：用户关心哪些元信息
  ④ 颗粒度：一部法一条，还是一批文件一条

输出
----
· 终端：摘要 + 每个表前 10 行样本
· 文件：`outputs/_cn_policy_dump.txt`（**全量**内容，UTF-8，供后续逐条分析）
"""
from __future__ import annotations

import io
import re
import sys
import math
import datetime
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "docs" / "中国电池回收政策法规标准20260907.xlsx"
OUT = ROOT / "outputs" / "_cn_policy_dump.txt"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# 标题措辞词频用的关键词表（中英文，覆盖中国电池回收政策语汇）
KEYS = [
    "电池", "回收", "梯次", "利用", "溯源", "拆解", "再生", "综合利用",
    "管理", "规范", "条件", "试点", "生产者", "责任", "白名单", "名单",
    "办法", "条例", "通知", "公告", "指南", "标准", "技术", "规范",
    "报废", "机动车", "新能源汽车", "动力", "储能", "固废", "固体废物",
    "危险废物", "危废", "碳", "护照", "编码", "运输", "安全", "环保",
    "环境", "评价", "检测", "分类", "标识", "污染", "许可", "审批",
    "暂行办法", "实施方案", "意见", "规划", "政策",
]

_buf: list[str] = []


def pr(*args: object) -> None:
    line = " ".join(str(a) for a in args)
    print(line)
    _buf.append(line)


def clean(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and math.isnan(v):
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%Y-%m-%d")
    return re.sub(r"\s+", " ", str(v)).strip()


def cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> int:
    try:
        import openpyxl  # noqa: PLC0415
    except ImportError:
        print("缺少 openpyxl：py -m pip install openpyxl")
        return 1
    if not XLSX.exists():
        print(f"找不到文件：{XLSX}")
        return 1

    wb = openpyxl.load_workbook(str(XLSX), read_only=True, data_only=True)
    pr("=" * 80)
    pr(f"工作簿：{XLSX.name}  |  {XLSX.stat().st_size:,} bytes")
    pr(f"工作表 {len(wb.sheetnames)} 个：{wb.sheetnames}")
    pr("=" * 80)

    all_titles: list[str] = []
    header_by_sheet: dict[str, list[str]] = {}

    for si, sn in enumerate(wb.sheetnames, 1):
        ws = wb[sn]
        rows = [[clean(c) for c in r] for r in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(x for x in r)]
        pr("")
        pr("#" * 80)
        pr(f"### 表 {si}：{sn}   有效行 = {len(rows)}")
        pr("#" * 80)
        if not rows:
            pr("（空表）")
            continue
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        header = rows[0]
        data = rows[1:]
        header_by_sheet[sn] = header
        pr(f"数据行数：{len(data)}")
        pr("")
        pr("--- 列清单 ---")
        for j, h in enumerate(header):
            vals = [r[j] for r in data if r[j]]
            pr(f"  [{j:>2}] {h or '(空表头)':<18} 非空={len(vals):<4} "
               f"唯一={len(set(vals)):<4} 样例: {cut(' / '.join(vals[:3]), 70)}")

        # 全量行 dump（写到文件；终端只显示前 10）
        pr("")
        pr("--- 全量内容（本段仅入文件，终端见前 10 行）---")
        pr("[表头] " + " | ".join(header))
        for i, r in enumerate(data, 1):
            pr(f"[{i:>4}] " + " | ".join(cut(x, 300) for x in r))
        pr("")
        pr("--- 终端样本（前 10 行）---")
        for i, r in enumerate(data[:10], 1):
            print(f"  [{i:>3}] " + " | ".join(cut(x, 80) for x in r))

        # 分类列分布
        pr("")
        pr("--- 分类列取值分布（取值 2~40 种）---")
        any_cls = False
        for j, h in enumerate(header):
            vals = [r[j] for r in data if r[j]]
            cnt = collections.Counter(vals)
            if 2 <= len(cnt) <= 40 and sum(cnt.values()) >= 4:
                any_cls = True
                pr(f"  >> 列[{j}] {h or '(空表头)'}（{sum(cnt.values())} 值 / {len(cnt)} 类）")
                for v, n in cnt.most_common(40):
                    pr(f"       {n:>4} × {cut(v, 70)}")
        if not any_cls:
            pr("  （无）")

        # 年份
        pr("")
        pr("--- 年份分布 ---")
        years = collections.Counter()
        for r in data:
            for v in r:
                m = re.match(r"^(19|20)\d{2}", v)
                if m:
                    years[v[:4]] += 1
                    break
        pr("  " + ", ".join(f"{k}:{v}" for k, v in sorted(years.items())) if years else "  （无）")

        # 标题列收集（用**列索引**，不用列名 —— 空表头会让 index() 崩掉）
        # ⚠️ 正则必须收窄到「名称/标题/题目」：
        #    首版写成 `标题|名称|文件|法案|政策|标准名称` —— 结果 "政策/标准"、
        #    "类型/法律层级"、"摘要"、"关联关系"等列全被当成标题列，
        #    收集出 999 条混杂"标题"（脏数据）。
        title_idx = [j for j, h in enumerate(header)
                     if re.search(r"标题|名称|题目", h or "")]
        if not title_idx:
            pr("  （本表无标题/名称列 —— 跳过标题收集，仍保留全量内容 dump）")
        sheet_titles: list[str] = []
        for j in title_idx:
            for r in data:
                if r[j]:
                    sheet_titles.append(r[j])
        all_titles.extend(sheet_titles)
        pr("")
        if title_idx:
            pr(f"--- 本表标题列索引：{title_idx}（"
               f"{[header[j] for j in title_idx]}）—— 本表收集 {len(sheet_titles)} 条"
               f"（全局累计 {len(all_titles)}）---")
    wb.close()

    # ===== 全局统计 =====
    pr("")
    pr("=" * 80)
    pr("=== 全局：标题全量清单 + 词频 ===")
    pr("=" * 80)
    pr(f"标题总数：{len(all_titles)}")
    pr("")
    kc = collections.Counter()
    for t in all_titles:
        for k in KEYS:
            if k in t:
                kc[k] += 1
    pr("--- 标题词频（出现该词的文件数）---")
    for k, c in kc.most_common():
        pr(f"  {k:<8} {c}")
    if all_titles:
        lens = sorted(len(t) for t in all_titles)
        pr("")
        pr(f"标题长度：min={lens[0]} 中位={lens[len(lens)//2]} "
           f"max={lens[-1]} 平均={sum(lens)/len(lens):.1f}")
    pr("")
    pr("--- 全部标题 ---")
    for i, t in enumerate(all_titles, 1):
        pr(f"  {i:>4}. {t}")

    OUT.write_text("\n".join(_buf), encoding="utf-8")
    print("")
    print(f"✅ 全量结果已写入 {OUT}（{len(_buf)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
