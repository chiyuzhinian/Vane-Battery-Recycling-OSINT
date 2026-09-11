"""用浏览器抓取被反爬拦截的站点（PHMSA / ECHA / CalRecycle / BCI 等）。

为什么需要这个脚本（实测 2026-09-10）
------------------------------------
这批站点对 httpx 与 curl 一律 403，但对真实浏览器放行：

    us_phmsa.dot.gov     403   ⭐ 退役电池/黑粉运输合规的唯一官方入口
    echa.europa.eu       403   ⭐ 黑粉危废定性
    calrecycle.ca.gov    403   ⭐ 州级 EPR 样板
    batterycouncil.org   403
    call2recycle.org     403

用法
----
    py scripts/collect_browser_sources.py --site phmsa
    py scripts/collect_browser_sources.py --site all
    py scripts/collect_browser_sources.py --site phmsa --download-pdfs

产出
----
    outputs/browser_<site>_<时间戳>.jsonl     正文证据
    sources/browser-captured/<site>/*.pdf     官方文档原文（下载成功时）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.connectors.browser import BrowserFetcher   # noqa: E402
from app.core.relevance_browser import judge_browser  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

OUT = ROOT / "outputs"
CAPTURED = ROOT / "sources" / "browser-captured"

# 硬超时：单站挂起不能拖死整批（实测 ECHA / Call2Recycle 会长时间无响应）
SITE_TIMEOUT = 90.0     # 单次页面导航/链接发现上限（秒）
FETCH_TIMEOUT = 60.0    # 单篇文档 / 单个 PDF 上限（秒）

# 超过这个字符数的相关文档，除了进 jsonl（截断）还要全文落盘。
# 实测触发案例：ECHA 的电池法规附件/物质限制清单 22.5 万字符。
BIG_DOC_CHARS = 20000

# ============================================================
# 站点定义：hub 页面 + 文档发现正则
# ============================================================
SITES: dict[str, dict] = {
    "phmsa": {
        "name": "DOT PHMSA - 锂电池运输安全（退役/回收/黑粉运输合规）",
        "region": "US",
        "hub": "https://www.phmsa.dot.gov/lithiumbatteries",
        # 只捞与"退役电池/回收/黑粉/DDR/托运"相关的文档，避免捞回一堆导航
        "doc_pattern": r"lithium|batter|disposal|recycl|ddr|damaged|defective|recalled|shipper|test summar",
        "cluster": "C6_transport_hazmat",
    },
    "echa": {
        "name": "ECHA - 电池法规相关（黑粉危废定性）",
        "region": "EU",
        # ⚠️ 实测（2026-09-11）：ECHA 的 Azure WAF 是 **JS 人机验证挑战**，
        #    不是硬拦截 —— 挑战跑完（约 6s）后页面正常加载。
        #    · /understanding-batteries-regulation → ✅ 电池法规正主页
        #    · /hot-topics/batteries                → 失效路径（挑战过后跳首页）
        #    · /regulations/batteries-regulation    → 404（原本就是死链）
        #    · /legislation                          → 200
        "hub": "https://echa.europa.eu/understanding-batteries-regulation",
        "extra_hubs": [
            "https://echa.europa.eu/legislation",
            "https://echa.europa.eu/support/guidance",
        ],
        "doc_pattern": r"batter|waste|recycl|hazard|legislat|regulat|annex",
        "cluster": "C3_black_mass",
    },
    "calrecycle": {
        "name": "加州 CalRecycle - 电池 EPR（全美样板）",
        "region": "US",
        # ⚠️ /bev/ 实测 404；/epr/ 实测 200（产品延伸责任总入口）
        "hub": "https://calrecycle.ca.gov/epr/",
        "extra_hubs": [
            "https://calrecycle.ca.gov/batteries/",
            "https://calrecycle.ca.gov/laws/legislation/",
        ],
        "doc_pattern": r"batter|recycl|stewardship|responsib|extended producer|legislat|law",
        "cluster": "C5_epr_collection",
    },
    # 说明：doc_pattern 是**链接发现**用的粗筛，故意放宽；
    #       最终相关性由 judge_browser 以页面身份（标题+URL）为准判定。
    #       両者职责不同：粗筛保召回，judge_browser 保精确率。
    "bci": {
        "name": "Battery Council International（州级立法推手）",
        "region": "US",
        "hub": "https://batterycouncil.org/",
        "doc_pattern": r"batter|recycl|policy|legislat|state",
        "cluster": "C5_epr_collection",
    },
    # ============================================================
    # 欧盟成员国层（法国）—— 补"成员国"这一层缺口
    # ------------------------------------------------------------
    # ⚠️ 实测（2026-09-11）：**法国政府站点普遍按国家/IP 封锁**。
    #    ademe.fr 主站直接回：
    #      "Access denied ... IP-based restriction, a country restriction,
    #       or the use of a VPN. Country: JP"
    #    本机出口 IP 归属地是 JP → 被地域封锁。
    #
    #    ⭐ 这与反爬是**完全不同的问题**：
    #       · 反爬       → 换浏览器/等挑战/改指纹，有解（PHMSA/ECHA 都解决了）
    #       · 地域封锁   → 本机怎么换都没用，只能换出口 IP 或走归档
    #    把两者混淆会白白花时间做浏览器对抗（做过，白费）。
    #
    #    ✅ 但有个例外：**ADEME 的开放数据门户没有被地域封锁**，
    #       而且对 OSINT 用途价值更高（结构化数据 > 网页宣传稿）。
    #    ❌ legifrance.gouv.fr：Cloudflare 挑战，有头+45s 也无法通过。
    #       法国法律文本的正确获取路径是 **EUR-Lex 的"成员国转化措施"
    #       (national transposition measures)**，而不是直连 Légifrance。
    # ============================================================
    "france": {
        "name": "法国 ADEME 开放数据（欧盟成员国层）",
        "region": "EU-MemberState",
        "hub": "https://data.ademe.fr/",
        "doc_pattern": r"batter|vhu|v[eé]hicule|vehicule|recycl|d[eé]chet|"
                       r"economie circulaire|mobilite|broyeur|producteur",
        "cluster": "C2_elv",
        # ⚠️ ADEME 的目录页是 JS 渲染的，fetch_links 抓不到数据集链接。
        #    所以用 seed_urls 直接给种子 —— 这些 URL 由 scripts/discover_sources.py
        #    定位（识别出 Data Fair 平台 → 调 API → 命中 REP-VHU 系列）。
        # ⚠️ slug 必须从 API 取**真值**，不能靠猜：
        #       https://data.ademe.fr/data-fair/api/v1/datasets?q=vhu
        #    猜过一次，5 个种子全部 404（"Page non trouvée"）。
        # ⭐ 后续更优解：ADEME 有可用的 REST API，应做成 API 连接器
        #    （`/data-fair/api/v1/datasets/<id>/lines` 可直接取数据行），
        #    而不是抓页面。浏览器通道是过渡方案。
        "seed_urls": [
            # 破碎厂吨位 —— 黑粉上游的直接量化指标 ⭐
            "https://data.ademe.fr/datasets/rep-vhu-tonnages-collectes-broyeurs-en-2018",
            # 破碎厂回收率/再利用率（TRR/TRV）⭐
            "https://data.ademe.fr/datasets/rep-vhu-trr-et-trv-des-broyeurs-en-2018",
            "https://data.ademe.fr/datasets/rep-vhu-tonnages-collectes-cvhu-en-2018",
            "https://data.ademe.fr/datasets/rep-vhu-trr-et-trv-des-cvhu-en-2018",
            "https://data.ademe.fr/datasets/rep-vhu-performances-cumulees-en-2018",
            # 生产者登记名录（竞争情报）⭐
            "https://data.ademe.fr/datasets/rep-vhu-liste-des-societes-inscrites-a-syderep",
            # VHU 材料按处理方式分布 ⭐
            "https://data.ademe.fr/datasets/materiaux-te-t1",
        ],
    },
}


async def collect_site(bf: BrowserFetcher, key: str, download_pdfs: bool) -> list[dict]:
    cfg = SITES[key]
    print(f"\n{'=' * 92}\n 🌐 {cfg['name']}\n {cfg['hub']}\n{'=' * 92}")

    records: list[dict] = []
    try:
        hub = await asyncio.wait_for(bf.fetch_text(cfg["hub"]), timeout=SITE_TIMEOUT)
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
        print(f"  ❌ hub 不可达/超时：{type(exc).__name__}")
        return records
    print(f"  hub: HTTP {hub.status} | {hub.title[:70]}")
    print(f"       正文 {len(hub.text)} 字符"
          + (f" | 日期线索 {hub.publish_date_hint}" if hub.publish_date_hint else ""))

    def add(url: str, title: str, text: str, status: int = 200,
            date_hint: str | None = None, kind: str = "page",
            challenge_failed: bool = False) -> None:
        # ⚠️ 必须用 judge_browser，不能用 judge_policy：
        #    浏览器抓的是整页渲染文本，全局导航会带来大量同母类噪声
        #    （实测 CalRecycle `/epr/` 把纺织/包装产品线都判成了相关）
        v = judge_browser(title, url, text)
        # ⚠️ 入库前的真实性门禁。
        #    不能用 `status != 200` 一刀切：WAF 的人机验证页状态码**也是 403**，
        #    但挑战通过后内容是真的（实测 ECHA）。
        #    因此改判「有没有拿到实质内容」，而不是「状态码好不好看」。
        if challenge_failed:
            reason = "waf_challenge_timeout"       # 等了但没通过 → 不是证据
        elif len((text or "").strip()) < 300:
            reason = f"content_too_short_{len((text or '').strip())}"
        else:
            reason = None
        if reason:
            records.append({
                "source_id": f"browser_{key}", "region": cfg["region"],
                "cluster": cfg["cluster"],
                "channel": "browser_capture", "kind": kind, "url": url,
                "title": title, "publish_date_hint": date_hint, "http": status,
                "text": "", "relevant": False, "score": 0.0,
                "needs_human_review": False, "hits": [],
                "rejected_by": reason,
            })
            return

        # ⭐ 大文档全文落盘。
        #   为什么必须在**这里**做（而不是循环结束后扫 records）：
        #   记录里的 text 已经截断到 6000，事后扫永远看不到真实长度。
        #   实测踩过这个坑：ECHA 的 22.5 万字符物质限制清单被静默裁掉。
        big_doc_path = None
        if v.relevant and len(text) >= BIG_DOC_CHARS:
            slug = re.sub(r"[^A-Za-z0-9._-]+", "-",
                          url.split("//")[-1].split("?")[0])[:90].strip("-")
            dest = CAPTURED / key / f"{slug}.txt"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(
                f"# {title}\n# {url}\n"
                f"# 抓取 {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
                f"（全文 {len(text)} 字符；jsonl 内仅前 6000）\n\n{text}",
                encoding="utf-8")
            big_doc_path = str(dest.relative_to(ROOT))
            print(f"    💾 全文落盘 {dest.name[:48]}（{len(text)} 字符）")
        records.append({
            "source_id": f"browser_{key}",
            "region": cfg["region"],          # 数据自带区域，下游无需维护映射表
            "cluster": cfg["cluster"],
            "channel": "browser_capture",
            "kind": kind,
            "url": url,
            "title": title,
            "publish_date_hint": date_hint,
            "http": status,
            "text": text[:6000],
            "text_len_full": len(text),          # 截断前长度，便于发现被裁的文档
            "full_text_path": big_doc_path,      # 大文档全文落盘位置（无则为 None）
            "relevant": v.relevant,
            "score": v.score,
            "needs_human_review": v.needs_human_review,
            "hits": v.hits[:6],
            "rejected_by": v.rejected_by,
        })

    add(cfg["hub"], hub.title, hub.text, hub.status,
        hub.publish_date_hint, kind="hub",
        challenge_failed=hub.challenge_failed)
    if hub.challenge_waited_ms:
        print(f"       JS 人机验证：等待 {hub.challenge_waited_ms} ms 后通过"
              if not hub.challenge_failed else
              f"       ⚠️ 人机验证等待 {hub.challenge_waited_ms} ms 仍未通过")
    pdf_pool: set[str] = set(hub.pdf_links)

    # 发现文档（主 hub + 备用入口，有些站点首页/栏目会改版导致 404）
    docs: list[dict] = []
    hubs = [cfg["hub"]] + list(cfg.get("extra_hubs") or [])
    for h in hubs:
        try:
            found = await asyncio.wait_for(
                bf.fetch_links(h, pattern=cfg["doc_pattern"]), timeout=SITE_TIMEOUT)
            print(f"  {h} → 发现 {len(found)} 个相关链接")
            docs += found
        except Exception as exc:  # noqa: BLE001
            print(f"  ⚠️ {h} 链接发现失败：{type(exc).__name__}")

    # 种子 URL：用于 JS 渲染目录页（如 ADEME Data Fair）——
    # 链接抓不到，直接给已知的数据集地址。
    for s in (cfg.get("seed_urls") or []):
        docs.append({"title": s.rstrip("/").split("/")[-1], "url": s})
    if cfg.get("seed_urls"):
        print(f"  种子 URL 注入 {len(cfg['seed_urls'])} 个（目录页 JS 渲染，链接不可发现）")
    # 去重（保序）
    deduped, seen_urls = [], set()
    for d in docs:
        if d["url"] not in seen_urls:
            seen_urls.add(d["url"])
            deduped.append(d)
    docs = deduped
    print(f"  合计相关链接 {len(docs)} 个")
    for d in docs[:12]:
        print(f"    · {d['title'][:76]}")

    # 逐篇抓取（限量，避免过久）
    for d in docs[:12]:
        try:
            doc = await asyncio.wait_for(bf.fetch_text(d["url"]), timeout=FETCH_TIMEOUT)
            pdf_pool.update(doc.pdf_links)          # 收集详情页里的 PDF 直链
            if len(doc.text) < 120:
                continue
            add(d["url"], doc.title or d["title"], doc.text, doc.status,
                doc.publish_date_hint, kind="document",
                challenge_failed=doc.challenge_failed)
            flag = "★" if doc.publish_date_hint else " "
            chal = (f"  [验证+{doc.challenge_waited_ms}ms]"
                    if doc.challenge_waited_ms and not doc.challenge_failed else "")
            print(f"    {flag} 抓取 {doc.title[:60]:<62} {len(doc.text):>6} 字符"
                  + (f"  (PDF×{len(doc.pdf_links)})" if doc.pdf_links else "")
                  + chal)
        except Exception as exc:  # noqa: BLE001
            print(f"    ⚠️ {d['url'][:70]} → {type(exc).__name__}")

    # 下载 PDF 原文
    if download_pdfs:
        for r in records:                                # 兜底：正文里出现的 PDF 链接
            pdf_pool.update(re_find_pdfs(r.get("text", "")))
        pdfs = sorted(pdf_pool)[:12]
        if pdfs:
            print(f"\n  📄 发现 {len(pdfs)} 个 PDF，尝试下载：")
        for p in pdfs:
            dest = CAPTURED / key / Path(p).name
            try:
                res = await asyncio.wait_for(bf.download(p, dest), timeout=FETCH_TIMEOUT)
                ok = "✅" if res["saved"] else "🚫"
                extra = f"  ← {res['reason']}" if res.get("reason") else ""
                print(f"    {ok} HTTP {res['status']} {res['bytes']:>8} B  "
                      f"{Path(p).name[:52]}{extra}")
            except Exception as exc:  # noqa: BLE001
                print(f"    ⚠️ {Path(p).name[:58]} → {type(exc).__name__}")

    return records


def re_find_pdfs(text: str) -> list[str]:
    import re
    return re.findall(r"https?://[^\s\"']+\.pdf", text or "")


async def main() -> int:
    ap = argparse.ArgumentParser(description="浏览器抓取被拦站点")
    ap.add_argument("--site", default="phmsa",
                    help="phmsa | echa | calrecycle | bci | all")
    ap.add_argument("--download-pdfs", action="store_true")
    ap.add_argument("--headful", action="store_true", help="显示浏览器窗口（调试用）")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    keys = list(SITES) if args.site == "all" else [args.site]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_records: list[dict] = []

    async with BrowserFetcher(headless=not args.headful) as bf:
        for k in keys:
            if k not in SITES:
                print(f"未知站点：{k}")
                continue
            try:
                all_records += await collect_site(bf, k, args.download_pdfs)
            except Exception as exc:  # noqa: BLE001
                print(f"  ❌ {k} 失败：{type(exc).__name__}: {exc}")

    path = OUT / f"browser_{args.site}_{stamp}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in all_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    rel = [r for r in all_records if r["relevant"]]
    print(f"\n{'=' * 92}")
    print(f" 合计 {len(all_records)} 条 → 相关 {len(rel)} 条")
    print(f" → {path.relative_to(ROOT)}")
    if rel:
        print("\n 相关条目：")
        for r in rel[:12]:
            date = f"[{r['publish_date_hint']}] " if r.get("publish_date_hint") else ""
            print(f"   · {date}{r['title'][:80]}")
            print(f"     {r['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
