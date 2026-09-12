# -*- coding: utf-8 -*-
"""27 国重扫 —— 基于 EUR-Lex「成员国转化措施」（NIM）统一索引。

为什么用 NIM 页而不是逐国爬
--------------------------
23 个小国没有官方 XML/API 通道，逐国建连接器成本极高且易碎。
而 EUR-Lex 的 NIM 页**一次覆盖全部 27 国**（+GB），每个转化措施条目带：
  · NIM 编号（EUR-Lex 全局唯一）→ 详情页 (?uri=NIM:id)
  · 标题（各国语言原文）
  · 公报引用（常在标题里，如 "M.B. du 06.02.2002, p. 4096"）

覆盖指令（边界内核心）：
  · 32000L0053 —— 报废车辆（ELV）指令
  · 32006L0066 —— 电池与蓄电池指令（2023/1542 的前身）
  （32023R1542 是法规，无转化措施 NIM —— 已验证重定向）

分层策略（多语言）
----------------
  tier1（自动相关 0.75）：标题含电池/车辆/黑粉词（24 语种词表）
  tier2（待人工 0.5）  ：标题只含废物/回收泛词
  其余 → 丢弃（不落盘）；判定命中可升级
近重复检查：与库内同国已有记录做标题前缀比对，重复者跳过并记录。

用法
----
    py scripts/collect_member_states_nim.py --dry-run     # 只看分层统计
    py scripts/collect_member_states_nim.py               # 抓取+判定+落盘
"""
from __future__ import annotations

import argparse
import asyncio
import glob
import html as html_mod
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.core.relevance import judge_portal_policy  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"
NIM_PAGE = "https://eur-lex.europa.eu/legal-content/EN/NIM/?uri=CELEX:{celex}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DIRECTIVES = [
    ("32000L0053", "ELV 报废车辆指令"),
    ("32006L0066", "电池与蓄电池指令"),
]

ALPHA3_TO_2 = {
    "BEL": "BE", "BGR": "BG", "CZE": "CZ", "DNK": "DK", "DEU": "DE",
    "EST": "EE", "IRL": "IE", "GRC": "GR", "ESP": "ES", "FRA": "FR",
    "HRV": "HR", "ITA": "IT", "CYP": "CY", "LVA": "LV", "LTU": "LT",
    "LUX": "LU", "HUN": "HU", "MLT": "MT", "NLD": "NL", "AUT": "AT",
    "POL": "PL", "PRT": "PT", "ROU": "RO", "SVN": "SI", "SVK": "SK",
    "FIN": "FI", "SWE": "SE",
    # GBR 不属于 EU27，跳过
}

# ---- 多语言对象词表 ----
BATT_RE = re.compile(
    r"batt|bater|patarei|\bakku|accumul|acumul|akumul|"
    r"\bpiles?\b|pilha|\belem\b|\btelep\b|μπαταρ|συσσωρευτ|"
    r"батери|акумулат", re.I)

ELV_RE = re.compile(
    r"end.of.life vehicle|v[eé]hicule.{0,12}hors|hors\s+d.?usage|\bvhu\b|vfu|"
    r"autowrak|afgedankte?\s+(?:voertuig|auto)|altfahrzeug|"
    r"fahrzeug|voertuig|v[eé]hicule|veicol|vozidl|vozil|j[aá]rmű|pojazd|"
    r"transporto priemon|transportlīdzek|sõiduk|ajoneuvo|k[øo]ret[øo]j|"
    r"fordon|veh[ií]culo|fuori uso|[όο]χημα|vettur|karozz|превозн|автомобил|"
    r"utranger|opušt|kasser|romu|elocast|dismantl|demolition|sloperij|"
    r"broyeur|schredder|schroot|shredder|"
    # ⚠️ 2026-09-12 实测补：北欧/中东欧盲区 ——
    #   遗漏整类数据：丹麦「汽车拆解报废+环保费」法律、瑞典「汽车报废令/
    #   汽车生产者责任」、捷克「寿命终止产品法」——都是 ELV 线的核心法规
    # ⚠️ 但 `ukončen` 单独用会误伤：「ukončením činnosti okresních úřadů」
    #   （终止区公所活动）被当成寿命终止 —— 已收窄为 `životnost`（寿命）
    r"\bbil|skrot|ophug|producentansvar|životnost", re.I)

WASTE_RE = re.compile(
    r"afval|abfall|d[eé]chet|waste|residu|rifiut|odpad|j[aä]te|avfall|"
    r"hullad[eé]k|recikl|recyc|recycl|verwertung|valorisation|smalti|"
    r"отпад|jäätm|atkritum|επεξεργασ|ανακύκλ|"
    # ⚠️ 同实测补：克/立「废物」、瑞典「废物管理」
    r"otpad|atliek|renh[aå]llning", re.I)

# 纯法令编号式标题（索引无主题词）→ 待人工：
#  实测：希腊「Acte législatif N° 15393/2332 - FEK1022…」、
#  葡「Decreto-Lei n° 196/2003 …」——标题只有编号，但从上下文
#  （ELV/电池指令的转化措施）看更可能是相关，交人工核实。
CITATION_ONLY_RE = re.compile(
    r"^(?:acte\s+l[ée]gislatif|d[ée]cret\s+(?:pr[ée]sidentiel|royal)|"
    r"decreto[- ]lei|loi\s+n|arr[êe]t[ée]\s+n)", re.I)


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def norm_title(s: str) -> str:
    """归一化标题（小写、去音标、去标点、取前 54 字符）用于近似重复检测。"""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", "", s.lower())
    return s[:54]


def parse_nim_index(page: str) -> list[dict]:
    """解析 NIM 索引页 → [{alpha3, country, nim, title}]。"""
    markers = [(m.start(), m.group(1))
               for m in re.finditer(r'id="([A-Z]{3})_transposition"', page)]
    out: list[dict] = []
    seen: set[str] = set()
    for i, (pos, alpha3) in enumerate(markers):
        end = markers[i + 1][0] if i + 1 < len(markers) else len(page)
        seg = page[pos:end]
        for m in re.finditer(r'href="[^"]*uri=NIM:(\d+)"[^>]*>([\s\S]*?)</a>', seg):
            nim, raw = m.group(1), m.group(2)
            title = clean_text(raw)
            if not title or nim in seen:
                continue
            seen.add(nim)
            out.append({"alpha3": alpha3, "nim": nim, "title": title})
    return out


def load_existing_titles() -> dict[str, set[str]]:
    """库内标题索引：国家码 → 归一化标题前缀集合。"""
    cc_by_source = {
        "de_gesetze": "DE", "nl_bwb": "NL", "browser_netherlands": "NL",
        "es_boe": "ES", "fr_dila": "FR", "fr_ademe_opendata": "FR",
        "browser_france": "FR",
    }
    idx: dict[str, set[str]] = {}
    for fp in sorted(glob.glob(str(OUT / "*.jsonl"))):
        if Path(fp).name.startswith("_"):
            continue
        for line in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            sid = r.get("source_id") or ""
            cc = cc_by_source.get(sid)
            if not cc:
                m = re.match(r"eu_nim_([a-z]{2})$", sid)
                cc = m.group(1).upper() if m else None
            if not cc:
                continue
            t = norm_title(r.get("title") or "")
            if len(t) >= 30:
                idx.setdefault(cc, set()).add(t)
    return idx


async def fetch(client: httpx.AsyncClient, url: str) -> str:
    for attempt in (1, 2, 3):
        try:
            r = await client.get(url, headers={"User-Agent": UA}, timeout=90)
            if r.status_code == 200 and len(r.content) > 10000:
                return r.text
            print(f"  ⚠️ HTTP {r.status_code} len={len(r.content)}（第 {attempt} 次）{url}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ {type(exc).__name__}（第 {attempt} 次）{url}")
        await asyncio.sleep(3)
    return ""


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    idx = load_existing_titles()
    n_existing = sum(len(v) for v in idx.values())
    print(f"库内成员国立标题索引：{n_existing} 条（{ {k: len(v) for k, v in sorted(idx.items())} }）\n")

    all_rows: list[dict] = []
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for celex, label in DIRECTIVES:
            print(f"=== {celex}（{label}）===")
            page = await fetch(client, NIM_PAGE.format(celex=celex))
            if not page:
                print("  ❌ 页面获取失败，跳过")
                continue
            entries = parse_nim_index(page)
            print(f"  解析 {len(entries)} 条转化措施")
            for e in entries:
                cc = ALPHA3_TO_2.get(e["alpha3"])
                if not cc:      # GBR 等非 EU27
                    continue
                e["country"] = cc
                e["directive"] = celex
                all_rows.append(e)
            await asyncio.sleep(2)

    print(f"\n合计 EU27 条目：{len(all_rows)}")

    # ---- 分层判定 ----
    tiers = {"tier1": 0, "tier2": 0, "drop": 0, "dup": 0}
    kept: list[dict] = []
    per_country: dict[str, dict] = {}
    for e in all_rows:
        st = per_country.setdefault(e["country"], {"total": 0, "tier1": 0,
                                                   "tier2": 0, "drop": 0, "dup": 0})
        st["total"] += 1

        nt = norm_title(e["title"])
        if nt and nt[:40] in {x[:40] for x in idx.get(e["country"], set())}:
            tiers["dup"] += 1
            st["dup"] += 1
            continue

        if BATT_RE.search(e["title"]) or ELV_RE.search(e["title"]):
            tier = 1
        elif WASTE_RE.search(e["title"]):
            tier = 2
        elif len(e["title"]) <= 110 and CITATION_ONLY_RE.search(e["title"]):
            tier = 2      # 法令编号式标题 —— 无法从标题判断，交人工
        else:
            tiers["drop"] += 1
            st["drop"] += 1
            continue

        v = judge_portal_policy(e["title"], e["title"])
        if v.relevant and not v.needs_human_review:
            relevant, score, review = True, max(v.score, 0.75), False
            hits, reason = v.hits[:4], None
        elif tier == 1:
            relevant, score, review = True, 0.75, False
            hits = [f"nim_tier1:{e['title'][:40]}"]
            reason = None
        else:
            relevant, score, review = True, 0.5, True
            hits = v.hits[:4] or [f"nim_tier2:{e['title'][:40]}"]
            reason = "转化措施·仅泛废物词命中 —— 待人工确认与退役电池/ELV 的关联"

        tiers[f"tier{tier}"] += 1
        st[f"tier{tier}"] += 1
        e.update({
            "relevant": relevant, "score": score, "review": review,
            "hits": hits, "reason": reason,
        })
        kept.append(e)

    print(f"\n分层：tier1 {tiers['tier1']}（自动相关）· "
          f"tier2 {tiers['tier2']}（待人工）· 重复跳过 {tiers['dup']} · "
          f"丢弃 {tiers['drop']}")
    print(f"落盘合计：{len(kept)}\n")

    print(f"{'国家':6s} {'总数':>4s} {'tier1':>5s} {'tier2':>5s} {'重复':>4s} {'丢弃':>4s}")
    for cc, st in sorted(per_country.items()):
        print(f"{cc:6s} {st['total']:>4d} {st['tier1']:>5d} {st['tier2']:>5d} "
              f"{st['dup']:>4d} {st['drop']:>4d}")

    if args.dry_run:
        print("\n（dry-run，未写盘）")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = OUT / f"eol_MS_nim_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for e in kept:
            f.write(json.dumps({
                "evidence_id": f"nim_{e['nim']}",
                "region": "EU",
                "channel": "connector",
                "source_id": f"eu_nim_{e['country'].lower()}",
                "cluster_hint": None,
                "url": f"https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=NIM:{e['nim']}",
                "title": e["title"],
                "publish_date": None,
                "publish_date_hint": None,
                "relevant": e["relevant"],
                "relevance_score": e["score"],
                "needs_human_review": e["review"],
                "hits": e["hits"],
                "rejected_by": None,
                "meta": {
                    "nim_id": e["nim"],
                    "country_alpha3": e["alpha3"],
                    "directive": e["directive"],
                    "source": "eur-lex NIM index (national transposition measures)",
                },
                "text": (f"NIM {e['nim']} · {e['country']} · 转化指令 {e['directive']}\n"
                         f"{e['title']}"),
                "review_reason": e["reason"],
            }, ensure_ascii=False) + "\n")
    print(f"\n→ {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
