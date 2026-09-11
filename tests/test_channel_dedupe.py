"""跨通道去重的单元测试 —— 直接跑：py tests/test_channel_dedupe.py

为什么必须有这个测试
--------------------
同一份数据会被**多个通道**各采一次，两个去重实现（`app/api/store.py` 与
`scripts/audit_collection_coverage.py`）原先都是"先到先得"。

实测后果（2026-09-12）：
```
ADEME 的 7 个数据集 URL 同时出现在
  · API 通道   fr_ademe_opendata（connector）—— 带字段与真数据行
  · 浏览器通道 browser_france（browser_capture）—— 整页渲染文本，导航噪声多
先到先得 → 保留的是**噪声更多的那个**，于是：
  · 审计误报「fr_ademe_opendata 零产出」
  · 面板上展示的也不是信息量更高的 API 版
```

这类 bug 不报错、不崩溃，**只在统计与展示层悄悄变差** —— 必须有断言兜住。

判据（必须与生产代码一致）：
    connector（结构化接口）> vane（通用搜索网页）> browser_capture（整页文本）
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api.store import DataStore, _channel_rank  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass

URL = "https://data.ademe.fr/datasets/rep-vhu-tonnages-collectes-broyeurs-en-2018"


def _row(channel: str, sid: str) -> dict:
    return {
        "url": URL,
        "evidence_id": f"ev-{sid}",
        "channel": channel,
        "source_id": sid,
        "title": f"{sid} title",
        "text": "battery " * 40,
        "relevant": True,
        "relevance_score": 1.0,
        "region": "EU",
        "publish_date": "2026-01-01",
    }


def _write(d: Path, name: str, rows: list[dict]) -> None:
    with io.open(d / name, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _load(d: Path) -> list[dict]:
    return DataStore(d, d / "review_decisions.jsonl").load(refresh=True)


def case_browser_first_connector_later() -> bool:
    """**真实场景**：早的那个文件里是 browser，晚的那个里是 connector。

    这与 ADEME 完全同形（先采到页面版，后采到 API 版）。
    """
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _write(d, "eol_EU_20260101_120000.jsonl",
               [_row("browser_capture", "browser_france")])
        _write(d, "eol_EU_20260101_130000.jsonl",
               [_row("connector", "fr_ademe_opendata")])
        recs = _load(d)
    ok = len(recs) == 1 and recs[0]["source_id"] == "fr_ademe_opendata"
    print(f"  A 先 browser 后 connector → 保留 {recs[0]['source_id'] if recs else '?'}"
          f"  （期望 fr_ademe_opendata）")
    return ok


def case_connector_first_browser_later() -> bool:
    """反向：connector 先到，browser 后到 → 不能被降级覆盖。"""
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _write(d, "eol_EU_20260101_120000.jsonl",
               [_row("connector", "fr_ademe_opendata")])
        _write(d, "eol_EU_20260101_130000.jsonl",
               [_row("browser_capture", "browser_france")])
        recs = _load(d)
    ok = len(recs) == 1 and recs[0]["source_id"] == "fr_ademe_opendata"
    print(f"  B 先 connector 后 browser → 保留 {recs[0]['source_id'] if recs else '?'}"
          f"  （期望 fr_ademe_opendata）")
    return ok


def case_vane_beats_browser() -> bool:
    """vane（通用搜索）应高于 browser_capture，但低于 connector。"""
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _write(d, "eol_EU_20260101_120000.jsonl",
               [_row("browser_capture", "browser_france")])
        _write(d, "eol_EU_20260101_130000.jsonl", [_row("vane", "vane")])
        _write(d, "eol_EU_20260101_140000.jsonl",
               [_row("connector", "fr_ademe_opendata")])
        recs = _load(d)
    ok = len(recs) == 1 and recs[0]["source_id"] == "fr_ademe_opendata"
    print(f"  C browser→vane→connector → 保留 "
          f"{recs[0]['source_id'] if recs else '?'}（期望 fr_ademe_opendata）")
    return ok


def case_same_rank_keeps_first() -> bool:
    """同一等级（两个 connector）→ 保留**先到的**（稳定，不来回抖）。"""
    with tempfile.TemporaryDirectory() as t:
        d = Path(t)
        _write(d, "eol_EU_20260101_120000.jsonl",
               [_row("connector", "fr_ademe_opendata")])
        _write(d, "eol_EU_20260101_130000.jsonl", [_row("connector", "es_boe")])
        recs = _load(d)
    ok = len(recs) == 1 and recs[0]["source_id"] == "fr_ademe_opendata"
    print(f"  D 同等级两条 → 保留 {recs[0]['source_id'] if recs else '?'}"
          f"（期望先到的 fr_ademe_opendata）")
    return ok


def case_rank_order() -> bool:
    """等级表本身：connector > vane > browser_capture > 未知。"""
    order = [
        _channel_rank({"channel": "connector"}),
        _channel_rank({"channel": "vane"}),
        _channel_rank({"channel": "browser_capture"}),
        _channel_rank({"channel": ""}),
        _channel_rank({}),
    ]
    ok = order[0] > order[1] > order[2] > order[3] == order[4] == 0
    print(f"  E 等级序 → {order}（期望严格递减，最后两个为 0）")
    return ok


CASES = [
    ("A browser 先到 / connector 后到", case_browser_first_connector_later),
    ("B connector 先到 / browser 后到", case_connector_first_browser_later),
    ("C browser→vane→connector 三级", case_vane_beats_browser),
    ("D 同等级保留先到", case_same_rank_keeps_first),
    ("E 等级序正确", case_rank_order),
]


def main() -> int:
    print("跨通道去重测试")
    print("=" * 60)
    passed = 0
    for name, fn in CASES:
        try:
            ok = fn()
        except Exception as exc:  # noqa: BLE001 —— 测试要报出异常而不是崩掉
            print(f"  {name} → 异常 {type(exc).__name__}: {exc}")
            ok = False
        passed += bool(ok)
    print("=" * 60)
    print(f"通过 {passed}/{len(CASES)}")
    return 0 if passed == len(CASES) else 1


if __name__ == "__main__":
    raise SystemExit(main())
