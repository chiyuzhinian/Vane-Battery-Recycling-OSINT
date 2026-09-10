"""数据源可达性 + 真实采集合验工具（Python 版）。

用法
----
    py scripts/verify_sources.py                    # 全量可达性探测
    py scripts/verify_sources.py --region CN        # 只看中国政策源
    py scripts/verify_sources.py --collect US       # 真实跑一遍美国采集并存证
    py scripts/verify_sources.py --collect EU       # 真实跑一遍欧盟采集并存证
    py scripts/verify_sources.py --json > report.json

它回答三个问题
--------------
    ① 能不能搜到？   → 每个源的真实 HTTP 状态 + 命中条数
    ② 搜到的是什么？ → --collect 把真实证据落盘到 outputs/
    ③ 源是真的吗？   → 调用 app/core/authenticity.py 做域名真实性判定

本脚本是"最终目标：搜索范围内全部都有并且正确"的第一道验证工具。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---- 允许从仓库根目录直接运行 ----
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import yaml  # noqa: E402

from app.connectors import get_connector  # noqa: E402
from app.core.authenticity import check_url  # noqa: E402
from app.core.relevance import judge  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台中文
except Exception:  # noqa: BLE001
    pass

SOURCES_DIR = ROOT / "sources"
OUTPUTS_DIR = ROOT / "outputs"
UA = "BatteryRecyclingOSINT/1.0 (+research; contact: chiyuzhinian)"


@dataclass
class Row:
    region: str
    source_id: str
    name: str
    domain: str
    http: int | None
    ms: int
    hits: int
    verdict: str            # REACHABLE | BLOCKED | FAILED | NO_URL
    authenticity: str       # official | industry | unknown | suspicious
    note: str = ""


@dataclass
class Report:
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    rows: list[Row] = field(default_factory=list)
    collected: dict[str, int] = field(default_factory=dict)

    @property
    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for r in self.rows:
            out[r.verdict] = out.get(r.verdict, 0) + 1
        return out


# ============================================================
# 加载配置
# ============================================================
def load_policy_sources(region: str | None) -> list[dict]:
    files = {
        "CN": "policy-cn.yaml",
        "EU": "policy-eu.yaml",
        "US": "policy-us.yaml",
    }
    out: list[dict] = []
    for rg, fn in files.items():
        if region and rg != region:
            continue
        path = SOURCES_DIR / fn
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for s in data.get("sources", []) or []:
            s.setdefault("region", data.get("region", rg))
            out.append(s)
    return out


# ============================================================
# 通用可达性探测
# ============================================================
async def probe_domain(client: httpx.AsyncClient, url: str, timeout: float = 25.0) -> tuple[int | None, int, str]:
    """返回 (status_code, elapsed_ms, note)。

    策略：先 httpx，遇 TLS/传输错误回退 curl.exe。
    原因：部分政府站点（gxt.hunan.gov.cn、ec.europa.eu）使用非标准 EC 曲线，
    Python 的 OpenSSL 会抛 bad ecpoint / DECRYPTION_FAILED，而 curl 正常。
    """
    import time as _t
    t0 = _t.monotonic()
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
        # 403 有可能是"只放行浏览器 UA"，用 curl + 浏览器 UA 再试一次
        if resp.status_code == 403:
            code, body_len = await _curl_fallback(url, timeout)
            if code and 200 <= code < 400:
                ms = int((_t.monotonic() - t0) * 1000)
                return code, ms, f"[浏览器UA回退] {body_len // 1024} KB  (httpx 403)"
        ms = int((_t.monotonic() - t0) * 1000)
        return resp.status_code, ms, _note_of(resp)
    except Exception as exc:  # noqa: BLE001
        code, body_len = await _curl_fallback(url, timeout)
        ms = int((_t.monotonic() - t0) * 1000)
        if code:
            return code, ms, f"[curl 回退] {body_len // 1024} KB  (httpx: {type(exc).__name__})"
        return None, ms, f"{type(exc).__name__}: {exc}"


def _note_of(resp: httpx.Response) -> str:
    if resp.status_code in (202, 403, 429):
        return f"疑似反爬 HTTP {resp.status_code}"
    if not resp.text.strip():
        return "空响应体"
    return f"{len(resp.content) // 1024} KB"


async def _curl_fallback(url: str, timeout: float) -> tuple[int | None, int]:
    """用 curl.exe 重试一次（Windows 上走 SChannel，TLS 兼容性更好）。"""
    import shutil
    exe = shutil.which("curl")
    if not exe:
        return None, 0
    proc = await asyncio.create_subprocess_exec(
        exe, "-s", "-L", "--max-time", str(int(timeout)),
        "-A", ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        "-o", "NUL", "-w", "%{http_code}|%{size_download}", url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await proc.communicate()
    try:
        code_s, size_s = out.decode().strip().split("|")
        code = int(code_s)
        return (code if code else None), int(size_s)
    except Exception:  # noqa: BLE001
        return None, 0


def verdict_of(code: int | None) -> str:
    if code is None:
        return "FAILED"
    if code in (202, 403, 429):
        return "BLOCKED"
    if 200 <= code < 400:
        return "REACHABLE"
    return "FAILED"


async def verify_policy_sources(region: str | None) -> list[Row]:
    sources = load_policy_sources(region)
    rows: list[Row] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        timeout=25.0,
    ) as client:
        sem = asyncio.Semaphore(6)          # 并发 6，做有礼貌的访问

        async def one(s: dict) -> None:
            url = s.get("entry") or s.get("api") or (
                f"https://{s['domain']}" if s.get("domain") else None
            )
            if not url:
                rows.append(Row(s.get("region", "?"), s.get("source_id", "?"),
                                s.get("name", ""), s.get("domain", ""),
                                None, 0, 0, "NO_URL", "unknown"))
                return
            async with sem:
                code, ms, note = await probe_domain(client, url)
            auth = check_url(url)
            rows.append(Row(
                region=s.get("region", "?"),
                source_id=s.get("source_id", "?"),
                name=s.get("name", ""),
                domain=s.get("domain", ""),
                http=code,
                ms=ms,
                hits=0,
                verdict=verdict_of(code),
                authenticity=auth.tier,
                note=note,
            ))

        await asyncio.gather(*(one(s) for s in sources))

    order = {"REACHABLE": 0, "BLOCKED": 1, "NO_URL": 2, "FAILED": 3}
    rows.sort(key=lambda r: (r.region, order.get(r.verdict, 9), r.source_id))
    return rows


# ============================================================
# 真实采集（走连接器）
# ============================================================
async def collect(region: str) -> dict[str, int]:
    """真实跑一遍连接器并把证据落盘。"""
    OUTPUTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stats: dict[str, int] = {}

    if region == "US":
        async with get_connector("us_federal") as conn:
            items = await conn.fetch(max_pages=2, per_page=20)
        stats["us_federal"] = len(items)
        _dump(items, OUTPUTS_DIR / f"us_federal_{stamp}.jsonl", region)

    elif region == "EU":
        async with get_connector("eur_lex") as conn:
            items = await conn.fetch("celex:32023R1542")
            items += await conn.fetch("keyword:battery", since="2025-01-01", limit=50)
        stats["eur_lex"] = len(items)
        _dump(items, OUTPUTS_DIR / f"eur_lex_{stamp}.jsonl", region)

    elif region == "CN":
        # 企业侧：巨潮资讯（上市公司公告）
        async with get_connector("cninfo") as conn:
            ann = await conn.fetch(max_pages=2, page_size=30)          # 全市场关键词
            ann += await conn.fetch("stock:002340", max_pages=1)       # 格林美
            ann += await conn.fetch("stock:300750", max_pages=1)       # 宁德时代（邦普母公司）
        stats["cninfo"] = len(ann)
        _dump(ann, OUTPUTS_DIR / f"cninfo_{stamp}.jsonl", "CN")

        # 企业侧：环评公示
        async with get_connector("eia") as conn:
            ev = await conn.fetch()
        stats["eia"] = len(ev)
        _dump(ev, OUTPUTS_DIR / f"eia_{stamp}.jsonl", "CN")

    return stats


def _dump(items: list, path: Path, region: str) -> None:
    """落盘 + 顺带跑一次相关性判定，直观看到"搜到的是不是我要的"。

    判定场景由每条证据的 meta.relevance_scenario 决定：
        eia（环评）→ "project"（项目类规则）
        其余        → "policy"（政策类规则）
    """
    kept, rejected, review = 0, 0, 0
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            scenario = it.meta.get("relevance_scenario", "policy")
            v = judge(it.raw_text, it.source_title, scenario=scenario)
            if v.relevant:
                kept += 1
                if v.needs_human_review:
                    review += 1
            else:
                rejected += 1
            record = {
                "evidence_id": it.evidence_id,
                "region": region,
                "source_id": it.source_id,
                "url": it.source_url,
                "title": it.source_title,
                "publish_date": it.publish_date.isoformat() if it.publish_date else None,
                "relevant": v.relevant,
                "relevance_scenario": scenario,
                "relevance_score": v.score,
                "rejected_by": v.rejected_by,
                "needs_human_review": v.needs_human_review,
                "review_reason": v.review_reason,
                "meta": it.meta,
                "text": it.raw_text[:800],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"  → 落盘 {path.relative_to(ROOT)}  "
          f"（相关 {kept}（待人工 {review}）/ 被拒 {rejected}）")


# ============================================================
# 输出
# ============================================================
def render(rows: list[Row]) -> None:
    print()
    print("=" * 108)
    print(f" 数据源可达性验证报告   {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 108)
    print(f"{'':2} {'区域':<4} {'source_id':<24} {'域名':<32} {'HTTP':<6}{'耗时':<8}{'真实性'}")
    print("-" * 108)
    icon = {"REACHABLE": "✅", "BLOCKED": "🚫", "FAILED": "❌", "NO_URL": "❔"}
    for r in rows:
        print(f"{icon[r.verdict]:<2} {r.region:<4} {r.source_id:<24} {r.domain:<32} "
              f"{str(r.http or '-'):<6}{str(r.ms) + 'ms':<8}{r.authenticity:<10} {r.note}")
    print("-" * 108)
    counts: dict[str, int] = {}
    for r in rows:
        counts[r.verdict] = counts.get(r.verdict, 0) + 1
    parts = " | ".join(f"{icon.get(k, '')} {k} {v}" for k, v in sorted(counts.items()))
    print(f" 合计 {len(rows)} 个源：{parts}")
    print()


async def main() -> int:
    ap = argparse.ArgumentParser(description="数据源可达性 + 真实采集合验")
    ap.add_argument("--region", choices=["CN", "EU", "US"], help="只验证某个区域")
    ap.add_argument("--collect", choices=["US", "EU", "CN"], help="真实跑一遍采集并落盘")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--probe-connectors", action="store_true",
                    help="额外探测连接器（cninfo/eia/eur_lex/us_federal）")
    args = ap.parse_args()

    if args.probe_connectors:
        from app.connectors import probe_all
        print("\n▶ 连接器探测")
        for pr in await probe_all():
            print(f"  {pr}")
            if pr.sample:
                print(f"      样例: {pr.sample}")

    if args.collect:
        print(f"\n▶ 真实采集：{args.collect}")
        stats = await collect(args.collect)
        print(f"  统计：{stats}")

    rows = await verify_policy_sources(args.region)
    if args.json:
        print(json.dumps(
            {"generated_at": datetime.now(timezone.utc).isoformat(),
             "rows": [asdict(r) for r in rows]},
            ensure_ascii=False, indent=2))
    else:
        render(rows)

    failed = sum(1 for r in rows if r.verdict == "FAILED")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
