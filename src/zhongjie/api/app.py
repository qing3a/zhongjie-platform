"""
FastAPI app factory
组装所有 router
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .routers import agents, audit, a2a, billing, candidates, delegations, tasks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App 启动/关闭 hook
    关键: 在 startup 阶段强制初始化 TrustStrategy，让其订阅 EventBus。
    否则: TrustStrategy 仅在 /api/agents/{id}/trust 等路由首次被访问时才创建,
         在此之前发出的所有事件 (delegation.placed/accepted/cancelled, task.completed/failed)
         都不会触发 trust score 调整。
    """
    from . import deps
    deps.get_event_bus()
    deps.get_agent_registry()
    deps.get_trust_strategy()
    logger.info("[lifespan] TrustStrategy 已订阅 EventBus, 事件驱动的 trust 调整已就绪")
    yield
    deps.reset_all()


def create_app() -> FastAPI:
    app = FastAPI(
        title="中介 API 平台 (zhongjie) - Agent 协作网络",
        version="1.0.0",
        description=(
            "新版本 FastAPI 应用 - 基于 P0-P5 重构的六层架构\n"
            "- /api/agents/*   Agent 管理 + A2A Card\n"
            "- /api/tasks/*    异步任务\n"
            "- /api/delegations/*  委托协作\n"
            "- /api/billing/*  账单与结算\n"
            "- /api/audit/*    治理决策审计\n"
            "- /a2a            A2A JSON-RPC 入口\n"
            "- /.well-known/agent-card.json  平台 Agent Card"
        ),
        lifespan=lifespan,
    )
    # 注册路由
    app.include_router(agents.router)
    app.include_router(candidates.router)
    app.include_router(tasks.router)
    app.include_router(delegations.router)
    app.include_router(billing.router)
    app.include_router(audit.router)
    app.include_router(a2a.router)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": app.version}

    @app.get("/")
    def root():
        return {
            "name": app.title,
            "version": app.version,
            "docs": "/docs",
            "endpoints": {
                "agents": "/api/agents",
                "candidates": "/api/candidates",
                "tasks": "/api/tasks",
                "delegations": "/api/delegations",
                "billing": "/api/billing/invoices",
                "audit": "/api/audit",
                "a2a": "/a2a",
                "platform_card": "/.well-known/agent-card.json",
            },
        }

    return app


# 默认 app 实例（方便 uvicorn 启动）
app = create_app()
