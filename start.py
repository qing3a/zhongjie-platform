#!/usr/bin/env python
"""
项目启动脚本

启动 zhongjie.api.app (新版本 FastAPI 应用)。

用法:
  python start.py                              # 监听 0.0.0.0:8000
  PORT=9000 python start.py                    # 自定义端口
  DATA_DIR=demo_run/data python start.py       # 自定义数据目录
  HOST=127.0.0.1 RELOAD=1 python start.py     # 开发模式 (autoreload)
"""
import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "0") == "1"

    from zhongjie.api.app import app
    from zhongjie import __version__
    print(f"[start.py] 中介 API 平台 v{__version__}: http://{host}:{port}/docs")
    print("  端点: /api/agents /api/candidates /api/tasks /api/delegations")
    print("        /api/billing /api/audit /a2a /.well-known/agent-card.json")

    uvicorn.run(app, host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
