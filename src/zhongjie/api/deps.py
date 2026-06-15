"""
FastAPI 依赖注入 - 服务单例
"""
import os
from functools import lru_cache
from pathlib import Path

from ..collaboration.delegation_service import DelegationManager, DelegationService
from ..collaboration.task_manager import TaskManager
from ..collaboration.task_service import TaskService
from ..domain.factory import build_services
from ..domain.services import CandidateService, JDService, MatchService
from ..governance.audit import AppendOnlyAuditLog
from ..identity.agent_card import AgentCard
from ..identity.registry import AgentRegistry
from ..infra.billing_service import BillingService
from ..infra.events import EventBus
from ..identity.trust_strategy import TrustStrategy


def get_data_dir() -> str:
    """读取数据目录: 每次访问都重读 env, 不缓存, 保证 DATA_DIR 修改即时生效
    默认 'data'。所有持久化相关的单例 (audit/task/delegation/domain) 都应通过此函数获取路径。
    """
    return os.environ.get("DATA_DIR", "data")


@lru_cache(maxsize=1)
def get_event_bus() -> EventBus:
    return EventBus()


@lru_cache(maxsize=1)
def get_agent_registry() -> AgentRegistry:
    return AgentRegistry(data_dir=get_data_dir())


@lru_cache(maxsize=1)
def get_trust_strategy() -> TrustStrategy:
    reg = get_agent_registry()
    bus = get_event_bus()
    return TrustStrategy(reg, bus)


def get_domain_services():
    """域服务 (jd/candidate/match) — 不缓存，data_dir 可能变"""
    raise NotImplementedError("通过 build_services_for_app 替代")


@lru_cache(maxsize=1)
def build_domain_services():
    jd_svc, cand_svc, match_svc = build_services(get_data_dir())
    return jd_svc, cand_svc, match_svc


@lru_cache(maxsize=1)
def get_task_manager() -> TaskManager:
    return TaskManager(data_dir=get_data_dir())


@lru_cache(maxsize=1)
def get_task_service() -> TaskService:
    return TaskService(get_task_manager(), event_bus=get_event_bus())


@lru_cache(maxsize=1)
def get_delegation_manager() -> DelegationManager:
    return DelegationManager(data_dir=get_data_dir())


@lru_cache(maxsize=1)
def get_delegation_service() -> DelegationService:
    _, cand_svc, _ = build_domain_services()
    return DelegationService(
        delegation_manager=get_delegation_manager(),
        candidate_service=cand_svc,
        event_bus=get_event_bus(),
        task_service=get_task_service(),
    )


@lru_cache(maxsize=1)
def get_billing_service() -> BillingService:
    return BillingService(data_dir=get_data_dir())


@lru_cache(maxsize=1)
def get_audit_log() -> AppendOnlyAuditLog:
    return AppendOnlyAuditLog(data_dir=get_data_dir())


def reset_all() -> None:
    """重置所有单例（测试用）"""
    get_event_bus.cache_clear()
    get_agent_registry.cache_clear()
    get_trust_strategy.cache_clear()
    build_domain_services.cache_clear()
    get_task_manager.cache_clear()
    get_task_service.cache_clear()
    get_delegation_manager.cache_clear()
    get_delegation_service.cache_clear()
    get_billing_service.cache_clear()
    get_audit_log.cache_clear()
