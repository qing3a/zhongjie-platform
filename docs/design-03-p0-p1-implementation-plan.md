# 交付物三：P0 解耦 + P1 身份层 可执行实施计划

> 目标：把 3 个巨石文件拆成六层模块化包，并建立 Agent 身份层。
> 原则：**渐进式**，老 API 全程可用，每个 PR 都可独立合入、独立回滚。
> 输入：交付物一（A2A 适配）+ 交付物二（委托场景）反推的需求。

---

## 0. 总览：两阶段、9 个里程碑

```
P0 解耦（约 1 周）                  P1 身份层（约 3-5 天）
─────────────────                  ─────────────────
M1 建包骨架                          M6 AgentCard 数据模型
M2 抽取领域层(L4)                    M7 Registry + Agent 存储
M3 抽取治理层(L3)                    M8 Token 携带 agent_id
M4 抽取基础设施(L1)                  M9 老接口兼容 + 迁移脚本
M5 三巨石瘦身 + 老 API adapter
```

每个里程碑：**独立 PR + 测试通过 + 老 API 不破**。

---

# 第一部分：P0 解耦

## 目标
240KB 三巨石（p0_core + p1_p2 + api_server）→ 六层模块包。**纯结构重组，零功能变更**。

## M1：建立包骨架（0.5 天）

### 产出目录
```
zhongjie/
├── src/zhongjie/
│   ├── __init__.py
│   ├── identity/        __init__.py  (空)
│   ├── governance/      __init__.py  (空)
│   ├── domain/          __init__.py  (空)
│   ├── collaboration/   __init__.py  (空)
│   ├── protocol/        __init__.py  (空)
│   ├── infra/           __init__.py  (空)
│   └── api/             __init__.py  (空)
├── pyproject.toml       (新增，src layout)
└── 老文件全部保留不动
```

### 验证
- `pip install -e .` 成功
- `python start.py` 仍能启动（老路径未动）

---

## M2：抽取领域层 L4（1.5 天）

**来源**：`api_server.py:1247-1444`（业务存储 + 4 个猎头 handler 里的领域逻辑）

### 迁移映射表（精确行号）

| 现有位置 | 迁移到 | 说明 |
|---------|--------|------|
| `api_server.py:1247-1249` `_jd_storage/_candidate_storage/_match_storage` | `domain/repositories.py` 的 `JDRepo/CandidateRepo/MatchRepo` | 从全局 dict 改为 Repository 类，**加 Lock** |
| `api_server.py:1251-1337` 持久化函数 | `infra/persistence.py` | 原子写逻辑搬走 |
| `api_server.py:1339-1358` `submit_jd` 领域部分 | `domain/jd.py::JDService.create()` | handler 只留 HTTP 壳 |
| `api_server.py:1360-1385` `submit_candidate` | `domain/candidate.py::CandidateService.create()` | 含 `mask_sensitive_data` |
| `api_server.py:1387-1423` `submit_match` | `domain/match.py::MatchService.create()` | |
| `api_server.py:1425-1444` `get_match_status` | `domain/match.py::MatchService.get()` | |

### 关键改动
- 全局 dict → Repository（依赖注入，可测试）
- **补上 Lock**（现有 `_jd_storage` 等无锁，非线程安全 —— 这是个现存 bug，顺手修）
- handler 函数签名不变，内部改为调 Service

### 验证
- `test_p1_p2.py` 全绿（39 个用例）
- curl `/skill/猎头_skill/submit_jd` 行为不变

---

## M3：抽取治理层 L3（1 天）

**来源**：`p0_core.py` 全部 + `p1_p2.py` 的规则/审批/路由部分

### 迁移映射表

| 现有位置 | 迁移到 |
|---------|--------|
| `p0_core.py:1-50` RequestStatus/ActionType/Request | `governance/models.py` |
| `p1_p2.py:87-91` ActionType 枚举 | `governance/models.py`（合并去重） |
| `p1_p2.py:184-227` Condition | `governance/rules.py` |
| `p1_p2.py:229-253` Rule | `governance/rules.py` |
| `p1_p2.py:1829-1971` RuleManager | `governance/rule_manager.py` |
| `p1_p2.py:433-610` MediatorAPI 的审批/路由方法 | `governance/approval.py` + `governance/routing.py` |
| `p1_p2.py:1602-1717` AuditLogManager | `governance/audit.py` |

### 兼容技巧
`p1_p2.py` 顶部加 re-export，老导入不断：
```python
# p1_p2.py（保留兼容）
from zhongjie.governance.rules import Condition, Rule, ActionType
from zhongjie.governance.models import RequestStatus, Request
```

### 验证
- `from p1_p2 import Rule, Condition` 仍可用
- 审批流程 e2e 跑通

---

## M4：抽取基础设施 L1（1 天）

**来源**：`p1_p2.py` 的各种 Manager

### 迁移映射表

| 现有位置 | 迁移到 |
|---------|--------|
| `p1_p2.py:2488-2643` PersistenceManager | `infra/persistence.py` |
| `p1_p2.py:611-709` BillingManager | `infra/billing.py` |
| `p1_p2.py:714-820` QuotaManager | `infra/quota.py` |
| `p1_p2.py:1494-1597` WebhookManager | `infra/webhooks.py` |
| `p1_p2.py:875-1001` CallbackManager | `infra/callbacks.py` |
| `p1_p2.py:1074-1269` RetryManager | `infra/retry.py` |
| `p1_p2.py:2379-2457` ConfigManager | `infra/config.py` |

### 验证
- 老的 `MediatorAPIP3.__init__`（p1_p2.py:1977）改为从新位置 import，行为不变

---

## M5：三巨石瘦身 + 老 API adapter（0.5 天）

### 动作
1. `api_server.py` 的 handler 改为薄壳，调 `domain/*Service`
2. `p1_p2.py` 变成纯 re-export shim（向后兼容）
3. `p0_core.py` 变成纯 re-export shim

### 最终 `api_server.py` 体积预期：123KB → ~30KB（只剩 router）

### 关键：协议 dispatcher 抽象
```python
# protocol/dispatcher.py
class ProtocolDispatcher(Protocol):
    def dispatch(self, request) -> Response: ...

class SkillLinkDispatcher:    # 老 /skill/* 走这里
class A2ADispatcher:          # 新 /a2a 走这里（P3 接入）
```
为交付物一的 A2A 适配预留接口。

### 验证
- **全量回归**：`pytest -v` + 手测 dashboard.html + curl 全部端点
- 三巨石可删可留（留作 shim）

---

# 第二部分：P1 身份层

## 目标
匿名 role → 具身 Agent。Token 携带 `agent_id`，领域模型加 `owner_agent_id`。

## M6：AgentCard 数据模型（0.5 天）

### 新建 `identity/agent_card.py`
```python
@dataclass
class AgentCard:
    agent_id: str               # "hh-A"，主键
    name: str
    role: Literal["headhunter","employer","platform"]
    capabilities: list[str]     # ["candidate_sourcing","finance"]
    tier: Literal["standard","silver","gold"]
    trust_score: float          # 0.0-1.0，初始 0.5
    tenant_id: str
    endpoint: str | None        # A2A 端点
    auth_scheme: str = "bearer"
    created_at: datetime
    status: Literal["active","suspended","revoked"]
```

### 验证
- 数据模型单测通过

---

## M7：Registry + 存储（1 天）

### 新建 `identity/registry.py`
```python
class AgentRegistry:
    def register(self, card: AgentCard) -> str: ...
    def get(self, agent_id: str) -> AgentCard | None: ...
    def update_trust(self, agent_id: str, delta: float): ...
    def list_by_capability(self, cap: str) -> list[AgentCard]: ...
    def revoke(self, agent_id: str): ...
```

### 存储
- 复用 `infra/persistence.py`，新增 `data/agents.json`
- 后续可平滑迁 SQLite

### 验证
- 注册/查询/吊销单测

---

## M8：Token 携带 agent_id（1 天）

### 改动 `auth.py`（精确锚点）

| 现有位置 | 改动 |
|---------|------|
| `auth.py:17-26` APIKey 字段 | 加 `agent_id: str \| None = None` |
| `auth.py:28-34` Token 字段 | 加 `agent_id: str \| None = None` |
| `auth.py:44` `generate_key_pair` 签名 | 加参数 `agent_id=None` |
| `auth.py:80` `_generate_token` | 把 agent_id 编入 token |
| `auth.py:99` `verify_token` | 解出 agent_id 填入 Token |
| `auth.py:241-253` check_permission | 保留，agent_id 作为补充维度 |
| **关键**：`auth.py:39-42` 内存存储 | 改为持久化（现有重启即丢，是 bug） |

### `get_current_token` 增强（api_server.py:526）
返回的 Token 现在带 agent_id，下游 handler 可拿到调用者身份。

### 验证
- 老 token（无 agent_id）仍能验证（兼容）
- 新 token 带 agent_id

---

## M9：老接口兼容 + 迁移（1 天）

### 三件事

**① 猎头 handler 注入身份**（api_server.py:1339-1444）
```python
@register_skill("猎头_skill")
def submit_jd(jd_data: dict, token: Token) -> dict:  # ← 加 token
    agent_id = token.agent_id  # 谁提交的
    return jd_service.create(jd_data, owner_agent_id=agent_id)
```

**② 领域模型加 owner 字段**
- `domain/candidate.py` Candidate 加 `owner_agent_id`
- `domain/jd.py` JD 加 `owner_agent_id`
- data/*.json 一次性迁移脚本：旧记录 `owner_agent_id = "legacy"`

**③ 数据迁移脚本** `scripts/migrate_add_owner.py`
```python
# 给所有现有 jd/candidate 补 owner_agent_id="legacy"
# 给所有现有 request 的 metadata 补 requester_agent_id
```

### 验证
- 老数据迁移后仍可查询
- 新提交的记录带 owner_agent_id
- 现有 dashboard.html 不破

---

# 验收总清单（P0+P1 完成 = 可进入协作开发）

## P0 解耦
- [ ] 六层包结构建立，`pip install -e .` 通过
- [ ] 三巨石瘦身为 shim 或 router 薄壳
- [ ] `test_p1_p2.py` 39 个用例全绿
- [ ] 老 `/skill/*` `/api/*` 端点全量回归通过
- [ ] 全局 dict 的线程安全问题修复

## P1 身份层
- [ ] AgentCard 模型 + Registry 可用
- [ ] Token 携带 agent_id，老 token 兼容
- [ ] Candidate/JD 带 owner_agent_id
- [ ] 4 个猎头 handler 能识别调用者
- [ ] 数据迁移脚本跑通，旧数据不丢
- [ ] dashboard.html 仍可用

## 反向验证（接入交付物二的委托场景骨架）
- [ ] 能注册 Agent-A、Agent-B 两张 AgentCard
- [ ] A 提交的 candidate 记 owner=hh-A
- [ ] 规则引擎能读 `agent.trust_score`（为委托场景的治理铺路）

---

# 风险与对策

| 风险 | 对策 |
|------|------|
| 拆分过程中引入 bug | 每个里程碑独立 PR + 全量回归；先搬不碰逻辑 |
| 老 API 兼容断裂 | 用 re-export shim，`from p1_p2 import X` 永远有效 |
| 数据迁移丢数据 | 迁移前自动备份 data/；脚本先 dry-run |
| 工期超预期 | M1-M5 可并行分给多人；M6-M9 串行 |
| 内存 Token 重启丢失（M8 修） | 优先修，这是现存 bug 不是新需求 |

---

# 执行建议

1. **今天就做**：M1 建包骨架（半小时见效，降低后续摩擦）
2. **本周做**：M2-M5 解耦（结构到位，功能不动）
3. **下周做**：M6-M9 身份层（开始让 Agent"有名字"）
4. **再之后**：进入交付物二的委托场景实现 + A2A 适配

**完成 P0+P1 后，项目就从"中介网关"变成了"可识别 Agent 的协作平台底座"，后续每加一个协作原语（委托/分润/转介绍）都是纯增量。**

---

要不要我现在就开始动手做 **M1（建包骨架）**？这是最安全的第一步，半小时内完成，不碰任何现有逻辑。
