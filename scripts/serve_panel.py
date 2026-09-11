"""启动面板 API（FastAPI + uvicorn）。

用法
----
    py scripts/serve_panel.py                # 默认 127.0.0.1:8010
    py scripts/serve_panel.py --port 8100
    py scripts/serve_panel.py --reload       # 开发热重载

⚠️ 端口约定：前端 **3100**、后端 **8010**。
    ⚠️ **不要用 8000** —— 已被另一个项目 lithium-intel（Docker）占用；
       且 Windows 上 `localhost` 优先解析为 `::1`，请求会落到它那边。
   **不要用 3000** —— 那是 Vane 的端口（本项目的通道 A）。
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="退役电池回收 OSINT 面板 API")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--reload", action="store_true", help="开发模式热重载")
    a = ap.parse_args()

    import uvicorn

    base = f"http://{a.host}:{a.port}"
    print("=" * 62)
    print(f"  面板 API   {base}")
    print(f"  接口文档   {base}/docs")
    print(f"  地图数据   {base}/api/map")
    print(f"  未归类告警 {base}/api/unmapped")
    print("=" * 62)
    print("  前端约定端口 3100 ｜ Vane 占用 3000（勿混用）")
    print()

    uvicorn.run("app.api.main:app", host=a.host, port=a.port, reload=a.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
