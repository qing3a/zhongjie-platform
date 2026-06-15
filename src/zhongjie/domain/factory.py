"""
工厂方法 - 一键创建领域服务
M2 阶段不强制使用，保留给 M5 集成时用
"""
from pathlib import Path
from functools import lru_cache

from .models import Candidate, JD, Match
from .repositories import InMemoryRepository
from .services import CandidateService, JDService, MatchService


@lru_cache(maxsize=1)
def build_services(data_dir: str = "data") -> tuple[JDService, CandidateService, MatchService]:
    """构建完整领域服务栈，data_dir 缓存"""
    base = Path(data_dir)
    jd_repo = InMemoryRepository[JD](
        data_dir=base, filename="jd.json", from_dict=JD.from_dict
    )
    cand_repo = InMemoryRepository[Candidate](
        data_dir=base, filename="candidates.json", from_dict=Candidate.from_dict
    )
    match_repo = InMemoryRepository[Match](
        data_dir=base, filename="matches.json", from_dict=Match.from_dict
    )

    # 启动加载
    jd_repo.load()
    cand_repo.load()
    match_repo.load()

    jd_svc = JDService(jd_repo)
    cand_svc = CandidateService(cand_repo)
    match_svc = MatchService(match_repo, jd_svc, cand_svc)
    return jd_svc, cand_svc, match_svc
