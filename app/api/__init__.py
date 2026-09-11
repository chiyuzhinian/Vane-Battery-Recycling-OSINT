"""面板后端 —— 只读聚合 + 人工审核 + 反哺闭环。

对外 HTTP 接口在 `main.py`（FastAPI），数据访问在 `store.py`。

⚠️ 本包**不修改** `outputs/*.jsonl`：那是「采集快照」，属于不可变的历史证据。
   人工审核另存 `outputs/review_decisions.jsonl`，读取时叠加。
"""
from app.api.store import DataStore

__all__ = ["DataStore"]
