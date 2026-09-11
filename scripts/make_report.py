"""把散落在 outputs/*.jsonl 的证据，变成一份**可读、可追溯**的政策法规报告。

为什么需要它
------------
采集到 1600+ 条证据，但 jsonl 不是情报。研究者的真实问题是：
    「我手上到底有哪些政策法规？原文在哪？」

这份报告回答三个问题：
    ① 采到了什么（按监管层级组织，不是按文件组织）
    ② 原文链接是什么（每条都可点开核查）
    ③ 还缺什么（覆盖缺口）

⚠️ 两个必须处理的数据问题
------------------------
1. **重复计数**：浏览器通道的记录同时出现在 `browser_*.jsonl`
   和 `eol_*.jsonl`（管线合并时写入）。**必须按 URL 去重**，
   否则"采了多少"会被虚高。
2. **真实性质疑**：报告里所有条目都来自已实测可达的官方源。
   非 200 响应、WAF 挑战页、模糊匹配噪声都已在采集层被拒，
   不会进入本报告。但**报告仍应标注来源可信度**，供人工取舍。

用法
----
    py scripts/make_report.py
    py scripts/make_report.py --out docs/policy-report.md --sample-n 8
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ⭐ 黑粉四条线的模式**必须与采集判定共用同一套**，否则会出现
#    "报告里显示的线"与"采集时判的线"不一致（会直接误导研究者）。
#    线名也从 relevance 导入 —— 曾因为报告里多写一个空格，
#    四条线全部显示"未收集到条目"（而实际有命中）。
from app.core.relevance import (  # noqa: E402
    LINE_DANGEROUS_GOODS,
    LINE_EOL_SHIPMENT,
    LINE_HAZWASTE,
    LINE_STRATEGIC,
    black_mass_lines,
)

OUT = ROOT / "outputs"
FULLTEXT_DIR = ROOT / "sources" / "eurlex-fulltext"


def fulltext_index() -> dict[str, dict]:
    """欧盟法规全文快照索引：CELEX → {path, chars}。

    为什么报告要标这个：**只有链接的报告无法回答"第 X 条规定了什么"**。
    有快照才能离线核查、引用条文、日后比对修订。
    """
    idx: dict[str, dict] = {}
    if not FULLTEXT_DIR.exists():
        return idx
    for p in sorted(FULLTEXT_DIR.glob("*.txt")):
        try:
            n = len(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        idx[p.stem] = {"path": p.relative_to(ROOT).as_posix(), "chars": n}
    return idx

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

# ============================================================
# 源目录：报告可读性的关键
# ------------------------------------------------------------
# 光给 source_id（如 `eu_eurlex_battery_reg`）没人看得懂；
# 必须翻译成「层级 + 机构 + 这份数据是什么」。
# ============================================================
SOURCE_CATALOG: dict[str, dict] = {
    # ---------- 欧盟一级立法 ----------
    "eu_eurlex_battery_reg": {
        "layer": "EU 一级立法", "jurisdiction": "欧盟",
        "org": "欧盟官方公报（EUR-Lex）", "credibility": 100,
        "what": "电池与废电池法规 (EU) 2023/1542 及关联立法",
    },
    "eu_eurlex_keyword": {
        "layer": "EU 一级立法", "jurisdiction": "欧盟",
        "org": "欧盟官方公报（EUR-Lex 关键词检索）", "credibility": 100,
        "what": "按关键词命中的欧盟立法/提案",
    },
    # ---------- 欧盟机构 ----------
    "browser_echa": {
        "layer": "EU 机构文件", "jurisdiction": "欧盟",
        "org": "欧洲化学品管理局（ECHA）", "credibility": 95,
        "what": "电池法规物质限制数据库（附件 I / 第 13(5) 条 / 附件 VI）",
    },
    # ---------- 成员国 ----------
    "de_gesetze": {
        "layer": "成员国法", "jurisdiction": "德国",
        "org": "德国联邦法律门户（官方 XML）", "credibility": 100,
        "what": "AltfahrzeugV 报废车法 / BattDG 电池法 / AVV 废物目录",
    },
    "fr_ademe_opendata": {
        "layer": "成员国数据", "jurisdiction": "法国",
        "org": "法国 ADEME（Data Fair API）", "credibility": 95,
        "what": "REP-VHU 报废车回收体系：破碎厂吨位、回收率、生产者名录",
    },
    "browser_france": {
        "layer": "成员国数据", "jurisdiction": "法国",
        "org": "ADEME 开放数据门户", "credibility": 95,
        "what": "报废车（VHU）回收数据集",
    },
    "browser_netherlands": {
        "layer": "成员国数据", "jurisdiction": "荷兰",
        "org": "Stichting OPEN（电池/电子生产者责任组织）", "credibility": 90,
        "what": "电池与电子废物收集绩效、WEEE 登记、回收企业动态",
    },
    # ---------- 美国联邦 ----------
    "us_federal_register": {
        "layer": "美国联邦", "jurisdiction": "美国",
        "org": "美国联邦公报（Federal Register）", "credibility": 100,
        "what": "DOE / EPA / IRS / DOT 的法规、通知与征询",
    },
    "browser_phmsa": {
        "layer": "美国联邦", "jurisdiction": "美国",
        "org": "DOT 管道与危险材料安全管理局（PHMSA）", "credibility": 100,
        "what": "退役电池与 DDR 电池的运输合规（黑粉运输线的唯一官方入口）",
    },
    # ---------- 美国州级 / 行业 ----------
    "browser_calrecycle": {
        "layer": "美国州级", "jurisdiction": "美国加州",
        "org": "CalRecycle", "credibility": 92,
        "what": "Responsible Battery Recycling Program（AB 2440）",
    },
    "browser_bci": {
        "layer": "美国行业", "jurisdiction": "美国",
        "org": "Battery Council International（铅电池协会）", "credibility": 82,
        "what": "铅电池回收率统计、州级立法动向",
    },
}

# 报告里按这个顺序呈现（监管层级由高到低）
LAYER_ORDER = ["EU 一级立法", "EU 机构文件", "成员国法", "成员国数据",
               "美国联邦", "美国州级", "美国行业", "其他"]

# ============================================================
# 黑粉监管四条线（本项目最核心的认知）
# ------------------------------------------------------------
# ⚠️ 模式本体在 `app/core/relevance.py` 的 BLACK_MASS_LINE_PATTERNS，
#    此处只保留**展示用的说明文案**。不要在这里再写一份模式 ——
#    两份模式一旦跑偏，报告与采集结果就会对不上。
# ============================================================
BLACK_MASS_LINES: list[dict] = [
    {"name": LINE_EOL_SHIPMENT,
     "hint": "黑粉在成员国之间运输、或出口到第三国时适用的规则",
     "why": "黑粉属于废物，跨境运输受《废物运输条例》(EU) 2024/1157 与巴塞尔公约约束"},
    {"name": LINE_DANGEROUS_GOODS,
     "hint": "按 UN 编号运输时的包装、文件与培训要求",
     "why": "黑粉与 DDR 电池属危险货物，美国归 49 CFR（PHMSA），欧洲归 ADR"},
    {"name": LINE_HAZWASTE,
     "hint": "黑粉是否按危险废物管理 —— 直接决定处置成本",
     "why": "定性不同，运输、存储、处置的许可与成本差一个量级"},
    {"name": LINE_STRATEGIC,
     "hint": "黑粉作为关键原材料回收能拿到的政策激励",
     "why": "欧盟关键原材料法 (EU) 2024/1252、美国 IRA 45X 都把回收料计入激励"},
]


def line_hits(rec: dict) -> list[str]:
    """复用采集层的四线判定，保证报告与采集一致。"""
    return black_mass_lines(rec.get("text") or "", rec.get("title") or "")


# 判断"是否与电池/黑粉直接相关"——用于把四线专题里的文件分两级。
# 只认具体词，不用泛词（如 "hazardous"/"transport"），否则等于没分。
BATTERY_CONTEXT_RE = re.compile(
    r"batter|lithium|li-?ion|black\s+mass|batterie|batterij|bateria|batteria|"
    r"altfahrzeug|vhu|shredder|schredder|broyeur|masse\s+noire|schwarzmasse|"
    r"cathode|anode|end-?of-?life\s+vehicle|\belv\b|accumulator|akkumulator",
    re.I)


def load_records() -> list[dict]:
    """加载全部证据并按 URL 去重。

    ⚠️ 跨文件有重复：浏览器记录同时在 `browser_*.jsonl` 与 `eol_*.jsonl`。
      按 URL 去重是唯一稳妥的口径（浏览器通道的 evidence_id 就是 URL 的 sha1）。
    """
    seen: set[str] = set()
    out: list[dict] = []
    files = (sorted(glob.glob(str(OUT / "eol_*.jsonl")))
             + sorted(glob.glob(str(OUT / "browser_*.jsonl")))
             + sorted(glob.glob(str(OUT / "policy_EU_*.jsonl")))
             + sorted(glob.glob(str(OUT / "policy_US_*.jsonl"))))
    for fp in files:
        for line in Path(fp).read_text(encoding="utf-8").splitlines():
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
    return out


def classify(rec: dict) -> tuple[str, dict]:
    """返回 (层级, 源元信息)。未登记的源归入「其他」。"""
    sid = rec.get("source_id") or "?"
    meta = SOURCE_CATALOG.get(sid)
    if meta:
        return meta["layer"], meta
    # 未登记：从 source_id 猜一个可读层级，并明确标注
    if sid.startswith("browser_"):
        layer = "其他"
    elif sid.startswith("eu_"):
        layer = "EU 一级立法"
    elif sid.startswith("us_"):
        layer = "美国联邦"
    else:
        layer = "其他"
    return layer, {"layer": layer, "jurisdiction": "未标注",
                   "org": sid, "credibility": 60,
                   "what": "未登记的源（建议补进 SOURCE_CATALOG）"}


def fulltext_line_hits() -> dict[str, list[str]]:
    """扫描全文快照库，返回 {黑粉线名: [CELEX, ...]}。

    ⚠️ 为什么必须扫全文而不只看 jsonl：
       jsonl 里只有元数据摘要（截断到 1200 字符），**不足以判定法规属于哪条线**。
       实测：黑粉第①条线在 jsonl 上长期为空，而《废物运输条例》全文里
       "shipments of waste" 出现 84 次。**结论要靠全文，不能靠摘要。**
    """
    out: dict[str, list[str]] = {}
    if not FULLTEXT_DIR.exists():
        return out
    for p in sorted(FULLTEXT_DIR.glob("*.txt")):
        try:
            txt = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in black_mass_lines(txt):
            out.setdefault(line, []).append(p.stem)
    return out


def matched_lines(rec: dict) -> list[str]:
    """判断这条证据命中黑粉监管的哪几条线（复用 relevance.py，单一事实来源）。"""
    return line_hits(rec)


# ============================================================
# 法规变更时间线
# ------------------------------------------------------------
# ⭐ 为什么"什么时候改了什么"比"现在是什么"更有情报价值：
#    实测电池法 (EU) 2023/1542 有 **14 个更正版本**（R(01)~R(14)），
#    持续到 2026 年仍在更正。对做合规的人来说，密集的更正意味着
#    **条文尚不稳定、执行口径仍在变** —— 这本身就是需要监测的信号。
# ============================================================
def build_timeline(records: list[dict]) -> list[dict]:
    """按法规主体聚合其全部版本（原始 + 更正 + 修订），形成时间线。"""
    groups: dict[str, dict] = {}
    for r in records:
        celex = str(((r.get("meta") or {}).get("celex") or "")).strip()
        if not celex:
            continue
        base = celex.split("R(")[0]
        g = groups.setdefault(base, {"base": base, "versions": [], "title": ""})
        is_corr = "R(" in celex
        kind = "更正" if is_corr else ("修订" if "L0" not in base[:1] else "原始")
        g["versions"].append({
            "celex": celex,
            "kind": "更正" if is_corr else "本体",
            "date": str(r.get("publish_date") or "")[:10],
            "title": r.get("title") or "",
            "url": r.get("url") or "",
        })
        if not is_corr and (r.get("title") or ""):
            g["title"] = r["title"]
    out = []
    for g in groups.values():
        g["versions"].sort(key=lambda v: v["date"] or "")
        g["n_corr"] = sum(1 for v in g["versions"] if v["kind"] == "更正")
        out.append(g)
    out.sort(key=lambda g: (-g["n_corr"], g["base"]))
    return out


# ============================================================
# 企业情报识别
# ------------------------------------------------------------
# ⭐ 为什么必须单独成章：企业侧信息（产能、融资、并购）对竞对分析的价值
#    **独立于政策**。混在政策清单里，研究者要翻 200 条联邦公报才能找到
#    一条"某回收商新开分选线"。
# ============================================================
COMPANY_SIGNALS: list[tuple[str, str]] = [
    (r"ouvre|opent|opens|opening|nouvelle\s+ligne|nieuwe\s+lijn|new\s+(production|sorting|recycling)\s+line",
     "产能扩张"),
    (r"investi|investering|investissement|Investition|funding|raise[sd]?\b|融资",
     "投融资"),
    (r"acquisition|acquires|acquiert|übernimmt|merger|fusión|合并|收购", "并购"),
    (r"partnership|samenwerking|partenariat|collaborat|cooperat", "合作"),
    (r"capacity|Kapazität|capacité|capaciteit|tonnes?\s+per\s+year|t/a\b", "产能指标"),
    (r"expands?|erweitert|agrandit|uitbreid", "扩产"),
]
_COMPANY_RE = [(re.compile(p, re.I), label) for p, label in COMPANY_SIGNALS]


def company_signals(rec: dict) -> list[str]:
    """识别企业动态信号。

    ⚠️ **必须排除法条与公报**：法律文本里天然包含 new / capacity / funding
    这类词，不排除会把《国家有害空气污染物排放标准》当成"投融资动态"。
    实测误报率极高，所以只对企业/行业/新闻类来源启用。

    企业情报的正确来源是：行业组织动态、企业公告、新闻报道 ——
    不是法规登记库。
    """
    sid = rec.get("source_id") or ""
    if sid in LEGAL_SOURCES:
        return []
    hay = f"{rec.get('title') or ''} {rec.get('text') or ''}"
    return sorted({label for rx, label in _COMPANY_RE if rx.search(hay)})


# 法规登记类来源：这些库里的文本是法条本身，不做企业动态识别。
LEGAL_SOURCES: set[str] = {
    "eu_eurlex_battery_reg", "eu_eurlex_keyword", "eu_eurlex",
    "de_gesetze", "fr_dila", "us_federal_register",
    "browser_echa", "browser_phmsa", "fr_ademe_opendata",
}


def render(records: list[dict], sample_n: int) -> str:
    rel = [r for r in records if r.get("relevant")]
    review = [r for r in rel if r.get("needs_human_review")]
    auto = [r for r in rel if not r.get("needs_human_review")]
    ft = fulltext_index()
    ft_lines = fulltext_line_hits()

    by_layer: dict[str, list[dict]] = defaultdict(list)
    for r in rel:
        layer, _ = classify(r)
        by_layer[layer].append(r)

    L: list[str] = []
    L += [
        "# 退役动力电池 / 报废汽车 / 黑粉 —— 欧美政策法规采集报告",
        "",
        f"生成时间：{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC　"
        f"（数据截止同上）",
        "",
        "> **阅读说明**：本报告只收录**已判定相关**的条目，每条都附原文链接，"
        "可直接点开核查。",
        "> 采集层已剔除：非 200 响应的拦截页、WAF 人机验证页、"
        "以及门户模糊匹配产生的噪声。",
        "",
        "---",
        "",
        "## 一、总览",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 去重后的证据条目 | {len(records)} |",
        f"| 判定为**相关** | **{len(rel)}** |",
        f"| 　其中高置信（自动判定） | {len(auto)} |",
        f"| 　其中待人工复核 | {len(review)} |",
        f"| 覆盖监管层级 | {len(by_layer)} |",
        f"| 欧盟法规全文快照 | **{len(ft)} 部**（可离线核查条文） |",
        "",
        "### 按监管层级分布",
        "",
        "| 层级 | 条目 | 主要机构 | 最高可信度 |",
        "|---|---:|---|---:|",
    ]
    for layer in LAYER_ORDER:
        items = by_layer.get(layer)
        if not items:
            continue
        orgs = Counter()
        cred = 0
        for r in items:
            _, meta = classify(r)
            orgs[meta["org"]] += 1
            cred = max(cred, meta.get("credibility", 0))
        top = "、".join(o for o, _ in orgs.most_common(2))
        L.append(f"| {layer} | {len(items)} | {top} | {cred} |")

    # ---------- 黑粉专题 ----------
    L += ["", "---", "",
          "## 二、黑粉监管四条线（本项目的核心结论）", "",
          "> **黑粉的监管不在电池法里**，而是分散在四条独立线上。",
          "> 不同的业务问题要引不同的法，下面把已收集的证据按线归位。", ""]
    for line in BLACK_MASS_LINES:
        hits = [r for r in rel if line["name"] in matched_lines(r)]
        ft_hits = ft_lines.get(line["name"], [])
        L += [f"### {line['name']} —— {line['hint']}", "",
              f"> 为什么归这条线：{line['why']}", ""]
        if ft_hits:
            L += [f"**法规全文命中（{len(ft_hits)} 部，已存本地快照）**", ""]
            for celex in ft_hits:
                info = ft.get(celex, {})
                src = next((r.get("url") for r in rel
                            if str(((r.get("meta") or {}).get("celex") or "")
                                   ).split("R(")[0] == celex), None)
                L.append(f"- **CELEX {celex}**"
                         + (f"（{info.get('chars', 0):,} 字符）" if info else ""))
                if src:
                    L.append(f"  - 在线原文：{src}")
                if info.get("path"):
                    L.append(f"  - 本地快照：`{info['path']}`")
            L.append("")
        if not hits and not ft_hits:
            L += ["_暂未收集到条目（覆盖缺口）_", ""]
            continue
        if not hits:
            continue

        # ⭐ 区分两级：只属该监管领域的 vs 且与电池/黑粉直接相关的。
        #   为什么必须分：像 "Hazardous Materials: Notice of Actions on Special
        #   Permits" 这类文件正文里有"危险货物法规"的样板文字，归②线没错，
        #   但对黑粉研究价值低。不区分会让专题被这类文件淹没。
        core, context = [], []
        for r in hits:
            blob = f"{r.get('title') or ''} {r.get('text') or ''}"
            if BATTERY_CONTEXT_RE.search(blob):
                core.append(r)
            else:
                context.append(r)

        def _emit(rows: list[dict], limit: int) -> None:
            for r in sorted(rows, key=lambda x: -(x.get("relevance_score") or 0))[:limit]:
                L.append(f"- **{(r.get('title') or '')[:120]}**")
                if r.get("publish_date"):
                    L.append(f"  - 日期：`{str(r['publish_date'])[:10]}`")
                L.append(f"  - 原文：{r.get('url')}")

        if core:
            L += [f"**与电池/黑粉直接相关（{len(core)} 条）**", ""]
            _emit(core, 6)
            L.append("")
        if context:
            L += [f"**属该监管领域、但未检出电池线索（{len(context)} 条）**",
                  "", "> 这些文件在正文里出现该领域的通用表述（如"
                      "\"危险货物法规\"样板文字），可能相关也可能无关，需人工判断。", ""]
            _emit(context, 3)
            if len(context) > 3:
                L.append(f"  - …另有 {len(context) - 3} 条")
            L.append("")

    # ---------- 分层清单 ----------
    L += ["---", "", "## 三、政策法规清单（按监管层级）", ""]
    for layer in LAYER_ORDER:
        items = by_layer.get(layer)
        if not items:
            continue
        _, meta = classify(items[0])
        L += [
            f"### {layer}",
            "",
            f"**机构**：{meta['org']}　**可信度**：{meta.get('credibility')}/100　"
            f"**条目**：{len(items)}　",
            f"**内容**：{meta.get('what')}",
            "",
        ]
        # 按来源再分组（同一层级可能有多个源）
        by_src: dict[str, list[dict]] = defaultdict(list)
        for r in items:
            by_src[r.get("source_id")].append(r)
        for sid, rows in by_src.items():
            _, m = classify(rows[0])
            if len(by_src) > 1:
                L += [f"#### {m['org']}（{len(rows)} 条）", ""]
            rows.sort(key=lambda x: (x.get("publish_date") or "",
                                     -(x.get("relevance_score") or 0)), reverse=True)
            for r in rows[:sample_n]:
                title = (r.get("title") or "（无标题）")[:130]
                date = (str(r.get("publish_date") or r.get("publish_date_hint") or "")
                        )[:10]
                flags = []
                if r.get("needs_human_review"):
                    flags.append("待复核")
                bm = matched_lines(r)
                if bm:
                    flags.append("黑粉线 " + "/".join(x[0] for x in bm))
                flag_s = f"　`{'、'.join(flags)}`" if flags else ""
                L.append(f"- **{title}**{flag_s}")
                L.append(f"  - {'日期 ' + date + '　' if date else ''}原文：{r.get('url')}")
                # 若这条对应某部已存全文快照的法规，标出来
                cx = (r.get("meta") or {}).get("celex")
                if cx:
                    base = str(cx).split("R(")[0]
                    if base in ft:
                        L.append(f"  - 全文快照：`{ft[base]['path']}`"
                                 f"（{ft[base]['chars']:,} 字符）")
            if len(rows) > sample_n:
                L.append(f"  - …另有 {len(rows) - sample_n} 条（共 {len(rows)} 条，"
                         f"见 `outputs/eol_*.jsonl`）")
            L.append("")

    # ---------- 欧盟法规全文库 ----------
    if ft:
        L += ["---", "", "## 四、欧盟法规全文库（可离线核查条文）", "",
              "> 只有链接的报告无法回答「第 X 条规定了什么」。",
              "> 下面这些法规已把**正文**抓下来存本地，可搜索、可引用、可日后比对修订。",
              "", "| CELEX | 正文长度 | 本地快照 | 在线原文 |", "|---|---:|---|---|"]
        for celex in sorted(ft):
            url = f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
            L.append(f"| `{celex}` | {ft[celex]['chars']:,} 字符 | "
                     f"`{ft[celex]['path']}` | {url} |")
        L += ["",
              "> 更新快照：`py scripts/fetch_eurlex_fulltext.py`"
              "（`--terms` 可按关键词扩充）", ""]

    # ---------- 法规变更时间线 ----------
    timeline = [g for g in build_timeline(records) if g["n_corr"] or len(g["versions"]) > 1]
    if timeline:
        L += ["---", "", "## 五、法规变更时间线", "",
              "> **「什么时候改了什么」比「现在是什么」更有情报价值。**",
              "> 频繁的更正意味着条文尚不稳定、执行口径仍在变 —— 这本身就是要监测的信号。",
              ""]
        for g in timeline[:8]:
            name = (g["title"] or g["base"])[:96]
            L += [f"### {name}", "",
                  f"主体 CELEX `{g['base']}`　共 {len(g['versions'])} 个版本"
                  f"（更正 {g['n_corr']} 次）", "",
                  "| 日期 | 版本 | CELEX |", "|---|---|---|"]
            for v in g["versions"][:14]:
                L.append(f"| {v['date'] or '—'} | {v['kind']} | `{v['celex']}` |")
            if len(g["versions"]) > 14:
                L.append(f"| … | 另有 {len(g['versions']) - 14} 个版本 | |")
            L += ["",
                  f"- 在线原文：https://eur-lex.europa.eu/legal-content/EN/TXT/"
                  f"?uri=CELEX:{g['base']}",
                  ""]

    # ---------- 企业情报 ----------
    comp = [(r, company_signals(r)) for r in rel]
    comp = [(r, s) for r, s in comp if s]
    if comp:
        L += ["---", "", "## 六、企业情报（与政策分开看）", "",
              "> 企业侧信息（产能、投融资、并购）对竞对分析的价值**独立于政策**。",
              "> 混在政策清单里，要翻几百条公报才能找到一条「某回收商新开分选线」。", "",
              "| 类型 | 标题 | 原文 |", "|---|---|---|"]
        for r, sig in sorted(comp, key=lambda x: -(x[0].get("relevance_score") or 0))[:20]:
            t = (r.get("title") or "")[:84].replace("|", "/")
            L.append(f"| {'、'.join(sig)} | {t} | {r.get('url')} |")
        L += ["", f"> 共 {len(comp)} 条含企业动态信号；"
                  f"识别规则见 `COMPANY_SIGNALS`（可按需扩充）", ""]

    # ---------- 原始文档 ----------
    captured = sorted((ROOT / "sources" / "browser-captured").rglob("*"))
    files = [p for p in captured if p.is_file()]
    if files:
        L += ["---", "", "## 七、其他已下载的原始文档", "",
              "| 文件 | 大小 | 来源站点 |", "|---|---:|---|"]
        for p in sorted(files, key=lambda x: -x.stat().st_size):
            rel_p = p.relative_to(ROOT)
            site = p.relative_to(ROOT / "sources" / "browser-captured").parts[0]
            kb = p.stat().st_size / 1024
            size = f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"
            L.append(f"| `{p.name}` | {size} | {site} |")
        L.append("")

    # ---------- 源健康度 ----------
    L += ["---", "", "## 八、数据源健康度", "",
          "| 源 | 层级 | 相关条目 | 命中率参考 |", "|---|---|---:|---|"]
    src_stat = Counter(r.get("source_id") for r in rel)
    for sid, n in src_stat.most_common():
        _, m = classify(rel[0]) if False else classify({"source_id": sid})
        L.append(f"| `{sid}` | {m['layer']} | {n} | — |")
    L += ["",
          "> 命中率口径说明：不同通道的采集方式不同（API 精准查询 vs 全文检索），",
          "> 跨通道比较命中率没有意义，故此处不列。同类通道内的命中率见 "
          "`outputs/eol_summary_*.md`。", ""]

    # ---------- 缺口 ----------
    L += ["---", "", "## 九、已知覆盖缺口", "",
          "| 缺口 | 说明 |", "|---|---|",
          "| 法国法规正文 | 已通 DILA 开放数据（日增量 0.9~1.8MB，已接入）；"
          "但 Légifrance 直连被 Cloudflare 拦截 |",
          "| 荷兰法规正文 | `wetten.overheid.nl` 可达但搜索是 JS 表单；"
          "需 BWB 编号或 SRU 连接名 |",
          "| 其他欧盟成员国 | 目前只覆盖德国、法国、荷兰；"
          "西班牙/意大利/波兰/比利时尚未接入 |",
          "| 美国州级立法 | 仅加州 CalRecycle；"
          "其他州（如华盛顿、缅因）的电池 EPR 法案未覆盖 |",
          "| 国际公约 | 巴塞尔公约（UNEP）源已登记但未纳入主管线 |",
          "| 行业数据库 | Fastmarkets / Benchmark 等付费源未接入（成本问题） |",
          "| 回收企业 | 目前仅有 Peperzeel（荷兰）一条企业产能情报，"
          "欧洲主要回收商（Umicore / Accurec / Duesenfeld）未系统覆盖 |",
          "",
          "> 成员国源的选择方法（重要）：**看有没有专业机构或结构化 API，"
          "而不是看有没有开放数据门户。**",
          "> 实测通用国家门户（govdata.de / dane.gov.pl）的全文搜索是"
          "**单字 OR 匹配**，搜\"报废车\"会返回\"职业介绍所登记册\"，垂直检索不可用。",
          ""]

    L += ["---", "",
          f"_本报告由 `scripts/make_report.py` 生成，数据源为 `outputs/*.jsonl`。_",
          "_重新生成：`py scripts/make_report.py`_", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="生成可读的政策法规采集报告")
    ap.add_argument("--out", default="", help="输出路径（默认 docs/policy-report-<日期>.md）")
    ap.add_argument("--sample-n", type=int, default=10,
                    help="每个源最多列多少条（默认 10，避免报告过长）")
    args = ap.parse_args()

    records = load_records()
    rel = [r for r in records if r.get("relevant")]
    print(f"载入 {len(records)} 条（已按 URL 去重），其中相关 {len(rel)} 条")

    md = render(records, args.sample_n)
    dest = Path(args.out) if args.out else (
        ROOT / "docs" / f"policy-report-{datetime.now():%Y-%m-%d}.md")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(md, encoding="utf-8")
    print(f"→ {dest.relative_to(ROOT)}（{len(md)} 字符）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
