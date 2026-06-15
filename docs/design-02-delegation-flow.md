# 交付物二：委托协作端到端链路设计
## 场景：猎头 A 把候选人委托给猎头 B 跟进

> 本文档用一个具体场景验证架构。走通这个场景，整套协作模型就立住了。
> 用 A2A Task 语义 + 现有治理层（规则引擎 + 审批台）实现。

---

## 1. 场景描述

**业务**：猎头 A（Agent-A）手上有个候选人，但 A 擅长互联网岗，这个候选人想做金融岗。A 把候选人**委托**给擅长金融的猎头 B（Agent-B）跟进。成功入职后，A、B 按约定分润（比如 4:6）。

**关键诉求**：
1. A 的候选人联系方式不能直接给 B（隐私 + 防飞单）→ 平台做**脱敏中介**
2. B 可以**接受/拒绝**委托（双向协作，不是派单）
3. 分润比例要**上链**（写入审计，不可篡改）
4. 甲方接触候选人的全程要**可追溯**

---

## 2. 角色与 Agent Card

| Agent | role | 本场景职责 |
|-------|------|-----------|
| Agent-A | headhunter | 委托发起方，持有候选人 |
| Agent-B | headhunter | 委托接收方，负责跟进 |
| Platform | platform | 中介 + 治理 + 分润结算 |
| Employer | employer | 最终用人单位（场景末端） |

---

## 3. 端到端时序（7 步）

```
Agent-A          Platform              Agent-B          Employer
   │  ①delegate     │                      │                │
   │───────────────▶│                      │                │
   │                │ ②治理(规则+信任)      │                │
   │  ③task:working │                      │                │
   │◀───────────────│  ④notify B           │                │
   │                │─────────────────────▶│                │
   │                │  ⑤B accept/reject    │                │
   │                │◀─────────────────────│                │
   │                │  ⑥B 推进(面试/offer)  │                │
   │                │◀──────state updates──│                │
   │                │  ⑦结算               │                │
   │  fee:40%       │         fee:60%      │                │
   │◀───────────────│─────────────────────▶│                │
```

### 步骤详解

**① 委托发起**（Agent-A → Platform）
```jsonc
// A2A tasks/send
{
  "method": "tasks/send",
  "params": {
    "skill": "delegate",
    "message": {
      "parts": [{
        "type": "data",
        "data": {
          "candidate_ref": "cand_a1",       // 引用，不含明文
          "target_agent_id": "hh-B",
          "jd_context": "金融 P7 数据岗",
          "fee_split": [{"agent_id":"hh-A","pct":0.4},
                         {"agent_id":"hh-B","pct":0.6}],
          "visibility": "masked",           // 联系方式脱敏
          "deadline": "2026-07-15"
        }
      }]
    }
  }
}
```
→ 平台生成 `task_id=task_del_001`，`context_id=ctx_finance_p7`

**② 治理层决策**（Platform 内部）
- 规则引擎（p1_p2.py:184-227 `Condition`）评估：
  - `agent-A.trust_score > 0.7` ✓
  - `agent-B.capabilities contains finance` ✓
  - `fee_split.sum == 1.0` ✓
- 命中 `auto_approve` → Task 进入 `working`
- 命中 `manual_review` → Task 进入 `input-required`，进审批台（复用现有 P1）

**③ 状态回执**（Platform → Agent-A）
```jsonc
{"result": {"task_id":"task_del_001", "state":"working",
            "context_id":"ctx_finance_p7"}}
```

**④ 通知 Agent-B**（Platform → Agent-B）
- 复用现有 `WebhookManager`（p1_p2.py:1494）或 A2A push notification
- B 收到一个"待响应委托"，本质是一个 `input-required` 子 Task

**⑤ Agent-B 接受/拒绝**（Agent-B → Platform）
```jsonc
// tasks/send 推进
{"params": {"taskId":"task_del_001",
            "message": {"parts":[{"data":{"decision":"accept",
                                          "note":"我有金融客户"}}]}}}
```
- accept → Task 继续 `working`，平台把**脱敏后**的候选人信息发给 B
- reject → Task → `failed`，通知 A，A 可改派他人

**⑥ 委托推进**（Agent-B 操作期间）
- B 把候选人推给甲方 → 平台记录 `sub_task: interview/offer`
- 每次状态变更，平台向 A 发推送（A 是 context 的关注方）
- 用 `tasks/sendSubscribe` 流式订阅，或 webhook

**⑦ 结算**（成功入职后）
- Task → `completed`
- `BillingManager`（p1_p2.py:611）按 `fee_split` 生成两条账单记录
- 写入审计（`AuditLogManager` p1_p2.py:1602），不可篡改

---

## 4. 数据模型新增（在现有基础上叠加）

### 4.1 Delegation（委托关系）—— 新实体
```python
@dataclass
class Delegation:
    id: str                      # deleg_xxx
    task_id: str                 # 关联 A2A Task
    context_id: str
    from_agent_id: str           # hh-A
    to_agent_id: str             # hh-B
    candidate_ref: str           # 指向 Candidate.id
    jd_context: str
    fee_split: list[FeeShare]    # [{agent_id, pct}]
    visibility: Literal["masked","full"]
    status: Literal["pending","accepted","rejected","in_progress",
                    "placed","cancelled"]
    created_at: datetime
    decided_at: datetime | None
```

### 4.2 Candidate 增强（现有 candidates.json 扩展）
```python
@dataclass
class Candidate:
    # 现有字段保留...
    owner_agent_id: str          # ← 新增：归属猎头
    shared_with: list[str]       # ← 新增：可见 agent
    provenance: list[Provenance] # ← 新增：来源链（防飞单）
    active_delegations: list[str]# ← 新增：当前委托中的 delegation_id
```

### 4.3 FeeShare / 结算
```python
@dataclass
class FeeShare:
    agent_id: str
    pct: float                   # 0.0-1.0，所有 share 之和必须=1.0
    settled: bool = False
    settled_at: datetime | None = None
```

---

## 5. 与现有系统的复用关系

| 现有组件 | 复用方式 |
|---------|---------|
| 规则引擎（Condition/Rule） | 写"委托授权规则"，如 trust_score 阈值、capability 匹配 |
| 审批台（P1） | 委托的 manual_review 直接进审批台 |
| WebhookManager | 委托状态变更通知 A、B 双方 |
| BillingManager | 按 fee_split 拆账（需从 tenant 维度改为 agent 维度） |
| AuditLogManager | 委托全链路审计 |
| `mask_sensitive_data`（api_server.py:1360） | 候选人脱敏，已有现成函数！ |

**结论**：这个场景 80% 的零件已存在，核心新增只是 `Delegation` 实体 + Agent 身份。

---

## 6. 隐私与防飞单设计（关键）

**问题**：B 拿到候选人后绕过平台私下联系 → 飞单。

**三层防护**：
1. **信息层**：`visibility=masked` 时，B 只看到脱敏信息（技能、年限、期望薪资），**看不到**电话邮箱。平台做"代为联系"。
2. **追溯层**：`Candidate.provenance` 记录"谁在何时接触过这个候选人"，任何面试邀约都带 delegation_id 签名。
3. **激励层**：`fee_split` 在委托发起时就上链审计，结算时强制按比例分。即使 B 飞单，A 也能凭审计记录主张权益。

---

## 7. 异常分支

| 情况 | 处理 |
|------|------|
| B 超时未响应（如 3 天） | Task 自动 → `failed`，A 可改派 |
| A 在委托中撤回 | `tasks/cancel`，若 B 已投入需结算补偿（规则定义） |
| 候选人被多个委托同时推进 | 同一 candidate 的 `active_delegations` 互斥校验 |
| 甲方最终没录用 | Task → `failed`，不结算，但记录 B 的投入（用于信任分） |
| 分润比例之和 ≠ 1.0 | 规则引擎在 ② 拦截，Task 直接失败 |

---

## 8. 验收标准（这个场景走通 = 架构成立）

- [ ] Agent-A 能发起委托，得到 task_id
- [ ] 治理层能 auto_approve 或转人工审批
- [ ] Agent-B 能收到通知并 accept/reject
- [ ] B accept 后收到的是**脱敏**候选人信息
- [ ] B 推进过程中 A 能收到状态推送
- [ ] 入职后 BillingManager 按 fee_split 出账
- [ ] 全程有审计日志，候选人 provenance 可查

---

## 9. 本场景暴露的架构需求（反推 P0/P1）

走通这个场景需要：
1. **Agent 身份**（A、B 是谁）→ 推动交付物三的 P1
2. **Candidate 所有权**（candidate_ref 指向谁的数据）→ 推动 P2 领域重构
3. **异步 Task**（委托是长流程）→ 推动 A2A 适配
4. **分润结算**（fee_split）→ 推动计费模块 agent 化

这四个需求就是下一份实施计划（交付物三）的输入。
