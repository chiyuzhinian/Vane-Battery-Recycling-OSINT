# -*- coding: utf-8 -*-
"""collect_at_ogd.py —— AT MODE A（DISCOVERY_EXPANSION）实采。

经官方 RIS OGD API（data.bka.gv.at，Batch 1R 恢复通道）枚举电池/废物
相关联邦法规，抓取文档（ogd.ris.bka.gv.at，HTML）入 corpus：

  sources/at-ogd/{NOR}.html        文档快照（附来源与哈希头注释）
  outputs/audit/at_ogd_inventory.json  枚举清单（Kurztitel/Eli/URL/相关性）

用法：py scripts/collect_at_ogd.py [--max-docs 6]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

AUDIT = ROOT / "outputs" / "audit"
OUTDIR = ROOT / "sources" / "at-ogd"
API = ("https://data.bka.gv.at/ris/api/v2.6/Bundesrecht"
       "?Applikation=BrKons&Suchworte={q}&Seitennummer={p}")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}

QUERIES = ["Batterie", "Altbatterie", "Abfallwirtschaft"]
RELEVANT = re.compile(r"batterie|lithium|akkumulator|altfahrzeug|abfall",
                      re.I)


def _walk(obj, key):
    """递归收集任意层级中 key 的值。"""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out += _walk(v, key)
    elif isinstance(obj, list):
        for x in obj:
            out += _walk(x, key)
    return out


def _iter_nodes(obj):
    """深度优先遍历所有 dict 节点。"""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _iter_nodes(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from _iter_nodes(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-docs", type=int, default=6)
    args = ap.parse_args()

    inventory: list[dict] = []
    seen: set[str] = set()
    with httpx.Client(headers=UA, timeout=40, follow_redirects=True) as cli:
        for q in QUERIES:
            for page in (1, 2):
                url = API.format(q=q, p=page)
                try:
                    r = cli.get(url)
                except Exception as exc:  # noqa: BLE001
                    print(f"  ⚠ {q} p{page}: {type(exc).__name__}")
                    continue
                if r.status_code != 200:
                    print(f"  ⚠ {q} p{page}: HTTP {r.status_code}")
                    continue
                try:
                    data = r.json()
                except Exception:  # noqa: BLE001
                    print(f"  ⚠ {q} p{page}: JSON 解析失败")
                    continue
                titles = _walk(data, "Kurztitel")
                elis = _walk(data, "Eli")
                doc_urls = [u["DokumentUrl"] for u in _iter_nodes(data)
                            if isinstance(u.get("DokumentUrl"), str)]
                for i, t in enumerate(titles):
                    eli = elis[i] if i < len(elis) else ""
                    doc = doc_urls[i] if i < len(doc_urls) else ""
                    nor = ""
                    m = re.search(r"(NOR\d+)", doc or "")
                    if m:
                        nor = m.group(1)
                    key = nor or f"{q}:{t[:60]}"
                    if key in seen:
                        continue
                    seen.add(key)
                    inventory.append({
                        "query": q, "page": page, "kurztitel": t,
                        "eli": eli, "doc_url": doc, "nor": nor,
                        "relevant": bool(RELEVANT.search(str(t))),
                    })
                print(f"  {q} p{page}: doc={len(titles)}")
                time.sleep(2)

        # 抓文档：相关性优先
        OUTDIR.mkdir(parents=True, exist_ok=True)
        ranked = sorted(inventory, key=lambda x: (not x["relevant"],))
        fetched = 0
        seq = 0
        for item in ranked:
            if fetched >= args.max_docs:
                break
            u = item.get("doc_url")
            if not u or not u.startswith("http"):
                continue
            seq += 1
            fn = OUTDIR / f"{item['nor'] or f'doc{seq:02d}'}.html"
            if fn.exists():
                fetched += 1
                continue
            try:
                r2 = cli.get(u)
            except Exception:  # noqa: BLE001
                continue
            if r2.status_code == 200 and len(r2.content) > 2000:
                fn.write_text(
                    f"<!-- source: {u}\n     eli: {item['eli']}\n"
                    f"     kurztitel: {item['kurztitel']}\n"
                    f"     fetched_at: "
                    f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ} -->\n"
                    + r2.text, encoding="utf-8")
                item["fetched_bytes"] = len(r2.content)
                item["final_url"] = str(r2.url)
                fetched += 1
                print(f"    ✅ {item.get('nor')} {len(r2.content)}B "
                      f"{str(item['kurztitel'])[:60]}")
            else:
                print(f"    ⚠ {item.get('nor') or u[-40:]} "
                      f"HTTP {r2.status_code} ({len(r2.content)}B)")
                # 兜底：对 ogd ELI 尝试 .html 变体
                mm = re.search(r"/(NOR\d+)$", u)
                if mm:
                    alt = ("https://ogd.ris.bka.gv.at/Dokumente/Bundesnormen/"
                           f"{mm.group(1)}/{mm.group(1)}.html")
                    try:
                        r3 = cli.get(alt)
                    except Exception:  # noqa: BLE001
                        r3 = None
                    if r3 is not None and r3.status_code == 200 \
                            and len(r3.content) > 2000:
                        fn.write_text(
                            f"<!-- source: {alt}\n     eli: "
                            f"{item['eli']}\n     kurztitel: "
                            f"{item['kurztitel']}\n     fetched_at: "
                            f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}"
                            f" -->\n" + r3.text, encoding="utf-8")
                        item["fetched_bytes"] = len(r3.content)
                        item["final_url"] = alt
                        fetched += 1
                        print(f"    ✅(alt) {item.get('nor')} "
                              f"{len(r3.content)}B")
            time.sleep(1.5)

    rel = [x for x in inventory if x["relevant"]]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "route": "RIS OGD API（data.bka.gv.at）+ 文档（ogd.ris.bka.gv.at）",
        "queries": QUERIES,
        "total": len(inventory), "relevant": len(rel),
        "fetched_docs": fetched,
        "inventory": inventory,
    }
    AUDIT.mkdir(parents=True, exist_ok=True)
    (AUDIT / "at_ogd_inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ 枚举 {len(inventory)}（相关 {len(rel)}）｜抓取 {fetched} 文档"
          f"→ sources/at-ogd/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
