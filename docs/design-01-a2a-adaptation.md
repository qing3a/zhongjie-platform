# 交付物一：A2A Protocol 协议适配设计（猎头场景）

> 目标：用开放标准 A2A（Agent2Agent）替代自研的 Skill Link，让猎头平台成为"Agent 协作网络"的一个节点。
> 本文档定义：协议映射、Agent Card 模型、Task 生命周期、与现有代码的对接点。

---

## 1. 为什么选 A2A

| 维度 | 当前 Skill Link | A2A Protocol |
|------|----------------|--------------|
| 语义 | 同步请求/响应 | 异步 Task 状态机（找候选人可能要几小时） |
| 身份 | 匿名 role 字符串 | Agent Card（具身能力声明） |
| 交互 | 单次 POST | `tasks/send` + 流式 `sendSubscribe` + 推送通知 |
| 标准 | 自研 | Linux Foundation 托管的开放标准（Google 2025-04 发起） |
| 生态 | 封闭 | 可与任意第三方 A2A Agent 互通 |

**结论**：Skill Link 降级为 A2A 的一个兼容层（legacy adapter），新能力全部建在 A2A 之上。

---

## 2. A2A 核心规范速览

### 2.1 Agent Card（能力声明）
- 服务于 `/.well-known/agent-card.json`
- 声明：身份、能力（skills）、鉴权方式、端点 URL

### 2.2 Task 生命周期
```
submitted → working → input-required → completed
                ↘ → failed
                ↘ → canceled
```
- `contextId`：把多个 Task 关联到同一业务上下文（如"为 JD-A 找候选人"）
- `taskId`：单个异步任务

### 2.3 JSON-RPC 2.0 方法
| 方法 | 作用 |
|------|------|
| `tasks/send` | 提交/推进一个 Task |
| `tasks/get` | 查询 Task 状态 |
| `tasks/sendSubscribe` | 提交并流式订阅更新（SSE） |
| `tasks/cancel` | 取消 Task |
| `tasks/pushNotification/set` | 注册 webhook 推送 |
| `message/send` | 无状态消息（轻量问答） |

---

## 3. 猎头平台 ↔ A2A 协议映射

### 3.1 三类 Agent 的 Agent Card

**① 猎头 Agent（HeadhunterAgent）**
```json
{
  "name": "智联猎头-AI",
  "description": "专注中高端技术岗的猎头 Agent",
  "version": "1.0.0",
  "capabilities": {"streaming": true, "pushNotifications": true},
  "skills": [
    {"id": "candidate_sourcing", "name": "候选人寻访",
     "inputModes": ["application/json"], "outputModes": ["application/json"]},
    {"id": "jd_matching", "name": "JD 匹配"}
  ],
  "authentication": {"schemes": ["bearer"]},
  "endpoint": "https://hh-a.example.com/a2a"
}
```

**② 甲方 Agent（EmployerAgent）**：skills = `jd_publish / interview_schedule / offer_decide`

**③ 平台 Agent（PlatformAgent，即本系统）**：skills = `delegate / settle_fee / audit / trust_query`

### 3.2 现有 Skill Action → A2A Task 映射

| 现有 Skill Link 动作 | A2A 等价 | Task 类型 |
|---------------------|---------|-----------|
| `猎头_skill/submit_jd` | `tasks/send` (skill=jd_publish) | 一次性，快速 completed |
| `猎头_skill/submit_candidate` | `tasks/send` (skill=candidate_sourcing) | **长任务**，working→completed |
| `猎头_skill/submit_match` | `tasks/send` (skill=jd_matching) | 一次性 |
| `猎头_skill/get_match_status` | `tasks/get` | 查询 |
| `甲方_skill/reply_interview` | `tasks/send` (skill=interview_schedule) | 一次性 |
| **新增：委托协作** | `tasks/send` (skill=delegate) | 长任务 + input-required |

### 3.3 统一响应格式对接

A2A 用 `JSON-RPC 2.0` 的 `result`/`error`。当前 Skill Link 的 `{status, code, data, message, meta}` 包成 JSON-RPC result：

```json
// A2A JSON-RPC 响应
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "status": "success",
    "code": "OK",
    "data": {"task_id": "task_xxx", "state": "working"},
    "message": "候选人寻访中",
    "meta": {"request_id": "req_xxx", "timestamp": "..."}
  }
}
```

---

## 4. 关键设计：Task 状态机适配现有 RequestStatus

现有 `RequestStatus`（p1_p2.py:88-93）：`pending / approved / rejected / routing / completed`

映射为 A2A Task state：

```
RequestStatus.pending      → TaskState.submitted      （提交，等治理）
治理 auto_approve          → working                  （规则放行，进入业务）
治理 manual_review         → input-required           （等人审批 ← 复用审批台！）
RequestStatus.rejected     → failed
RequestStatus.routing      → working                  （业务执行中）
RequestStatus.completed    → completed
```

**洞察**：现有"审批台（manual_review）"天然就是 A2A 的 `input-required`，治理层可以无缝接入 Task 状态机。这是迁移最大的便利点。

---

## 5. 与现有代码的对接点（行号锚点）

| 现有位置 | 改造方式 |
|---------|---------|
| `api_server.py:2210` FastAPI app | 新增 `/a2a` JSON-RPC router，与 `/skill` 并存 |
| `api_server.py:2313-2376` Skill dispatch | 抽象成 `ProtocolDispatcher`，A2A 和 Skill Link 各一个实现 |
| `p1_p2.py:88-93` RequestStatus | 新增 `TaskState` 枚举，与 RequestStatus 双向映射 |
| `p1_p2.py:105-128` Request 类 | 新增 `task_id / context_id / state` 字段 |
| `p1_p2.py:184-227` Condition | 规则引擎可直接用于 A2A Task 的治理决策 |
| `auth.py:28-34` Token | 新增 `agent_id` claim（详见交付物三） |
| `p1_p2.py:1494-1597` WebhookManager | **直接复用**为 A2A push notification 后端 |

---

## 6. 兼容策略（重要）

**不破坏现有 API**，新旧并行：

```
旧客户端 → /skill/{name}/{action}  → LegacySkillAdapter  → 业务逻辑
新 Agent → /a2a (JSON-RPC)         → A2AAdapter           ↗
```

两个 adapter 共享同一套领域服务（L4），只是协议翻译层不同。这样：
- 老的 dashboard.html、curl 示例继续可用
- 新的 A2A Agent 可以无缝接入
- 迁移可渐进，不搞大爆炸

---

## 7. 待研究 / 风险

- [ ] A2A 的 `Artifacts`（任务产物）如何承载"候选人简历"这种大对象？可能需要外部 URL 引用
- [ ] 多 Agent 协商时，谁是 Task 的"权威持有者"？建议：发起方持有，接收方镜像
- [ ] 当前 `WebhookManager` 是同步 HTTP，A2A 推送需要补 SSE 长连接（`sendSubscribe`）

---

## 参考资料
- [Agent2Agent (A2A) Protocol Specification – Official](https://a2a-protocol.org/latest/specification/)
- [Life of a Task – A2A Protocol](https://a2acn.com/en/docs/topics/life-of-a-task/)
- [Core Protocol Specification – agent2agent.info](https://agent2agent.info/specification/core/)
- [A2A Protocol Specification (Python)](https://medium.com/@vampirenalan/a2a-protocol-specification-python-0df3cfe67bec)
