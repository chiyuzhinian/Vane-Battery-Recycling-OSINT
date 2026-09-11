"""一次性探针：打印 EUR-Lex SPARQL 返回 400 时的**响应体**。

背景
----
`fetch_celex_batch` 日志只有 `ConnectorError`，`base.py` 又丢掉了 body，
所以"批量 2/4/5/8/9 反复失败"一直是黑盒。单独写探针跑出来是 **HTTP 400**，
不是超时 —— 那 body 里就有 Virtuoso 的原始报错。

对照实验设计
------------
  A. 单前缀（短的）—— 基线，应当成功
  B. 单前缀（可疑的）—— 看是否单个就挂
  C. 4 个前缀组合（与生产 chunk=4 一致）—— 看是否"组合"才挂

判定：
  · A 成功 + B 失败        → 是**某个前缀**的问题
  · A/B 都成功 + C 失败    → 是**组合长度/正则规模**的问题
  · 全失败                 → 是**查询模板本身**或端点限流的问题

用法
----
    py scripts/probe_sparql_400.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.connectors.eur_lex import Q_CELEX_BATCH, SPARQL_ENDPOINT  # noqa: E402

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept": "application/sparql-results+json, application/json;q=0.9, */*;q=0.8",
}


def probe(pattern: str, label: str) -> int | None:
    query = Q_CELEX_BATCH.format(pattern=pattern, limit=1500)
    print(f"\n--- {label} ---")
    print(f"    pattern 长度 {len(pattern)} / query 长度 {len(query)}")
    try:
        r = httpx.get(
            SPARQL_ENDPOINT,
            params={"query": query,
                    "format": "application/sparql-results+json"},
            headers=HEADERS,
            timeout=180.0,
            follow_redirects=True,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"    ❌ 传输异常 {type(exc).__name__}: {str(exc)[:200]}")
        return None

    print(f"    status={r.status_code}  bytes={len(r.content)}")
    if r.status_code >= 400:
        # ⭐ 这就是我们要的：Virtuoso 的原始报错
        print(f"    body: {r.text[:800]}")
        return r.status_code
    try:
        rows = r.json()["results"]["bindings"]
        print(f"    ✅ rows={len(rows)}")
        for b in rows[:5]:
            print(f"       · {b.get('celex', {}).get('value')}")
    except Exception:  # noqa: BLE001
        print(f"    ⚠️ 非 JSON：{r.text[:300]}")
    return r.status_code


def main() -> int:
    cases: list[tuple[str, str]] = [
        # A. 基线：一个普通前缀
        (re.escape("32023R1542"), "A. 单前缀 32023R1542（基线）"),
        # B. 采集日志里"批次 2 起始"的前缀
        (re.escape("32024R1252"), "B. 单前缀 32024R1252（批次2起始）"),
        # B2. 采集日志里"批次 4/5 起始"的前缀（含转义括号）
        (re.escape("52025PC0501R(01)"), "B2. 单前缀 52025PC0501R(01)"),
        (re.escape("32018L0849"), "B3. 单前缀 32018L0849"),
        # C. 4 个前缀组合（生产形状）
        ("|".join(re.escape(p) for p in
                  ["32024R1252", "32024R1781", "32025R1561", "32026R1738"]),
         "C. 4 前缀组合"),
        # D. 极端对照：8 个前缀组合（旧 chunk=6~8 的形状）
        ("|".join(re.escape(p) for p in
                  ["32024R1252", "32024R1781", "32025R1561", "32026R1738",
                   "52025PC0258", "52025PC0501", "32018L0849", "32020L0362"]),
         "D. 8 前缀组合"),
    ]
    statuses: list[int | None] = []
    for pat, label in cases:
        statuses.append(probe(pat, label))

    print("\n" + "=" * 60)
    ok = [s for s in statuses if s == 200]
    bad = [s for s in statuses if s and s >= 400]
    print(f"成功 {len(ok)} / 失败 {len(bad)} / 异常 {statuses.count(None)}")
    if bad:
        print("结论：400 是**确定性**的，原因见上方 body（Virtuoso 原始报错）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
