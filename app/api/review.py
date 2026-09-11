"""人工审核 —— 待审清单、提交、撤销。

⭐ 核心设计：**绝不修改原始采集数据**
    `outputs/*.jsonl` 是「采集快照」，属于不可变的历史证据。
    审核结果另存 `outputs/review_decisions.jsonl`，读取时叠加：

        有效判定 = 审核决定 ?? 机器判定

    为什么必须分离（而不是就地改 relevant 字段）：
      · 保留机器判定 → 能回溯「当初为什么这么判」，也是诊断采集方案的依据
      · 人工决定可撤销 → 误点可回退，且不需要备份/恢复原始文件
      · 机器重跑时不丢人工结果 → 重采后仍能看到哪条被人改判过

**两种 target_type**
    record —— 单条证据（`target_id` = `evidence_id`）
    source —— 整个数据源在该国范围内的全部记录（`target_id` = `source_id`）
              ⚠️ 源级决定会作用于该源**全部**记录，UI 必须二次确认
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

VALID_VERDICTS = ("relevant", "irrelevant", "uncertain")
VALID_TARGETS = ("record", "source")


class ReviewStore:
    """审核决定的读写。append-only 追加；撤销通过重写实现。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # ------------------------------------------------------------ 读
    def load(self) -> dict[str, dict]:
        """target_id → 决定（同一 target 后写的覆盖先写的）。

        ⚠️ 与 `app/api/store.py::DataStore._load_decisions()` 的索引方式保持一致，
           否则前端看到的有效判定与真正生效的判定会对不上。
        """
        out: dict[str, dict] = {}
        if not self.path.exists():
            return out
        try:
            text = io.open(self.path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            return out
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            tid = d.get("target_id")
            if tid:
                out[tid] = d
        return out

    def all_rows(self) -> list[dict]:
        rows: list[dict] = []
        if not self.path.exists():
            return rows
        try:
            text = io.open(self.path, encoding="utf-8").read()
        except (OSError, UnicodeDecodeError):
            return rows
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    # ------------------------------------------------------------ 写
    def submit(self, decisions: Iterable[dict], reviewer: str = "user") -> list[dict]:
        """批量提交。返回落盘后的记录（含生成的 decision_id）。

        校验失败会抛 ValueError，**整批拒绝**（不做部分写入——
        部分成功会让前端状态与后端不一致，很难排查）。
        """
        prepared: list[dict] = []
        for d in decisions:
            tt = d.get("target_type")
            tid = (d.get("target_id") or "").strip()
            verdict = d.get("verdict")
            if tt not in VALID_TARGETS:
                raise ValueError(f"target_type 必须是 {VALID_TARGETS} 之一，收到 {tt!r}")
            if not tid:
                raise ValueError("target_id 不能为空")
            if verdict not in VALID_VERDICTS:
                raise ValueError(f"verdict 必须是 {VALID_VERDICTS} 之一，收到 {verdict!r}")
            prepared.append({
                "decision_id": uuid.uuid4().hex[:16],
                "target_type": tt,
                "target_id": tid,
                "verdict": verdict,
                "reason": (d.get("reason") or "")[:200],
                "country": d.get("country"),
                "reviewer": reviewer,
                "decided_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

        if not prepared:
            return []

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for p in prepared:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        return prepared

    def revoke(self, decision_ids: list[str]) -> int:
        """撤销指定决定（按 decision_id）。返回实际删除条数。

        实现为**重写文件**：保留其余行。审核文件规模在万行级，
        重写成本远低于维护墓碑标记的复杂度。
        """
        want = set(decision_ids)
        if not want:
            return 0
        rows = self.all_rows()
        kept = [r for r in rows if r.get("decision_id") not in want]
        removed = len(rows) - len(kept)
        if removed:
            with self.path.open("w", encoding="utf-8") as f:
                for r in kept:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return removed

    def revoke_last(self, n: int) -> list[str]:
        """撤销**最近 N 条**（用于 UI 的「撤销上一批操作」）。

        返回被撤销的 decision_id 列表。
        """
        rows = self.all_rows()
        if not rows or n <= 0:
            return []
        # 文件是 append-only，末尾就是最近的
        victims = [r.get("decision_id") for r in rows[-n:] if r.get("decision_id")]
        self.revoke(victims)
        return victims

    # ------------------------------------------------------------ 统计
    def stats(self) -> dict[str, Any]:
        rows = self.all_rows()
        by_verdict: dict[str, int] = {v: 0 for v in VALID_VERDICTS}
        by_target: dict[str, int] = {t: 0 for t in VALID_TARGETS}
        for r in rows:
            v = r.get("verdict")
            if v in by_verdict:
                by_verdict[v] += 1
            t = r.get("target_type")
            if t in by_target:
                by_target[t] += 1
        return {
            "total": len(rows),
            "by_verdict": by_verdict,
            "by_target": by_target,
            "path": str(self.path),
        }
