# 中介 API 平台 - 数据模型设计

## 核心实体

### 1. Request (请求)
```json
{
  "id": "req_xxxxx",
  "source": "猎头_skill",
  "target": "甲方_skill",
  "intent": "职位匹配",
  "payload": {
    "jd": { ... },
    "candidate": { ... }
  },
  "metadata": {
    "workflowId": "wf_xxx",
    "userId": "user_xxx",
    "timestamp": "2026-05-31T10:00:00Z",
    "priority": "normal"
  },
  "status": "pending|approved|rejected|routing|completed"
}
```

### 2. Rule (规则)
```json
{
  "id": "rule_001",
  "name": "高管职位需人工审批",
  "priority": 10,
  "conditions": [
    {"field": "payload.jd.level", "op": "==", "value": "C-Level"},
    {"field": "source", "op": "in", "value": ["猎头_skill", "HR_skill"]}
  ],
  "action": "manual_review",
  "approvers": ["admin"],
  "enabled": true
}
```

### 3. Approval (审批记录)
```json
{
  "id": "apr_xxxxx",
  "requestId": "req_xxxxx",
  "ruleId": "rule_001",
  "decidedBy": "admin",
  "decision": "approved|rejected",
  "comment": "ok",
  "createdAt": "...",
  "decidedAt": "..."
}
```

### 4. Route (路由)
```json
{
  "id": "route_001",
  "requestId": "req_xxxxx",
  "from": "猎头_skill",
  "to": "甲方_skill",
  "forwardedPayload": { ... },
  "status": "sent|delivered|read|replied|error",
  "replyPayload": null
}
```

### 5. Workflow (工作流注册)
```json
{
  "id": "wf_xxxxx",
  "name": "猎头匹配流程",
  "skill": "猎头_skill",
  "enabled": true,
  "apis": [
    {"intent": "职位匹配", "endpoint": "/job/match", "method": "POST"},
    {"intent": "简历投递", "endpoint": "/resume/submit", "method": "POST"}
  ]
}
```

---

## 数据流图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           中介 API 平台                                 │
│                                                                         │
│  ┌──────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │ 接入方A   │───▶│              │    │             │    │ 目标方B  │ │
│  │ 猎头_skill│    │   Gateway    │───▶│  规则引擎   │───▶│ 甲方_skill│ │
│  └──────────┘    │              │    │             │    └──────────┘ │
│                  └──────────────┘    └──────┬──────┘                  │
│                          │                │                          │
│                          ▼                ▼                          │
│                  ┌──────────────┐  ┌─────────────┐                   │
│                  │   审批队列    │  │  自动通过   │                   │
│                  │ (人工审批台)  │  │             │                   │
│                  └──────┬───────┘  └─────────────┘                   │
│                         │                                             │
│                         ▼                                             │
│                  ┌──────────────┐                                    │
│                  │   路由分发    │                                    │
│                  └──────────────┘                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 规则引擎执行流程

```
请求进入
    │
    ▼
┌───────────┐
│ 遍历规则  │◀────── 按 priority 排序
└─────┬─────┘
      │
      ▼
┌─────────────────┐
│ 条件命中?       │
└─────┬───────────┘
      │
   Yes │                No
      ▼                  │
┌──────────┐             │
│ 执行action│            │
│ (见下表) │             │
└─────┬────┘             │
      │                  │
      ▼                  ▼
┌──────────┐       ┌───────────┐
│ 终止遍历  │       │ 检查下一条│
└──────────┘       └─────┬─────┘
                         │
                         ▼
                   ┌───────────┐
                   │ 无命中规则 │
                   └─────┬─────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ 默认: 人工审批│
                  └─────────────┘
```

---

## Action 类型

| Action | 行为 |
|--------|------|
| `auto_approve` | 直接通过，进入路由 |
| `auto_reject` | 直接拒绝，通知接入方 |
| `manual_review` | 放入审批队列，等待人工 |
| `route_directly` | 无需审批，直接路由到目标 |
| `enrich_then_review` | 先补充信息，再审批 |

---

## 状态机

### Request 状态流转
```
pending → approved → routing → completed
    │         │
    │         ▼
    │      rejected
    │
    ▼
manual_review → approved → routing → completed
              → rejected
```

---

## 猎头场景数据模型

### 核心实体

#### 1. JobDescription (职位 JD)
```json
{
  "id": "jd_xxxxx",
  "company": "甲方公司",
  "title": "高级工程师",
  "level": "P6",
  "salary_range": {"min": 30, "max": 50, "currency": "万/年"},
  "location": "北京",
  "requirements": ["5年+经验", "熟悉Python", "本科+"],
  "description": "负责系统架构设计...",
  "urgent": false,
  "created_by": "甲方_skill",
  "created_at": "2026-05-31T10:00:00Z"
}
```

#### 2. Candidate (候选人)
```json
{
  "id": "cand_xxxxx",
  "name": "张三",
  "phone": "138****1234",
  "email": "zhang***@email.com",
  "current_company": "A公司",
  "current_title": "工程师",
  "experience_years": 6,
  "education": "硕士",
  "expected_salary": 45,
  "expected_location": "北京",
  "skills": ["Python", "Go", "系统设计"],
  "created_by": "猎头_skill",
  "created_at": "2026-05-31T10:00:00Z"
}
```

#### 3. MatchRequest (匹配请求)
```json
{
  "id": "match_xxxxx",
  "source": "猎头_skill",
  "target": "甲方_skill",
  "intent": "job_match",
  "payload": {
    "jd_id": "jd_xxxxx",
    "candidate_id": "cand_xxxxx",
    "match_score": 0.85,
    "highlights": ["同行业经验", "技术栈匹配"],
    "猎头备注": "候选人近期在看机会"
  },
  "sensitive_fields": ["phone", "email"],
  "metadata": {
    "workflowId": "猎头匹配流程",
    "submitted_at": "2026-05-31T10:00:00Z"
  }
}
```

#### 4. Interview (面试安排)
```json
{
  "id": "interview_xxxxx",
  "match_id": "match_xxxxx",
  "stage": "初面",
  "scheduled_at": "2026-06-05T14:00:00Z",
  "location": "线上",
  "interviewer": "甲方技术总监",
  "status": "scheduled",
  "feedback": null
}
```

---

### 猎头场景数据流

```
猎头_skill                              中介平台                          甲方_skill
    │                                       │                                │
    │──────── 提交 JD ─────────────────────▶│                                │
    │                                       │                                │
    │◀─────── JD ID ────────────────────────│                                │
    │                                       │                                │
    │──────── 提交候选人 ───────────────────▶│                                │
    │                                       │ （脱敏：phone/email 打码）       │
    │◀─────── Candidate ID ──────────────── │                                │
    │                                       │                                │
    │──────── 提交匹配请求 ─────────────────▶│                                │
    │        (JD ID + Candidate ID)         │                                │
    │                                       │                                │
    │                        ┌───────────────▼───────────────┐                │
    │                        │     规则引擎审批              │                │
    │                        │  1. 匹配度 < 0.6 → 自动拒绝    │                │
    │                        │  2. 高管职位 → 人工审批        │                │
    │                        │  3. 其他 → 自动通过           │                │
    │                        └───────────────┬───────────────┘                │
    │                                        │                                │
    │◀─────── 审批结果 ───────────────────────│                                │
    │                                       │                                │
    │                                       │──────── JD + 候选人信息（脱敏）──▶│
    │                                       │                                │
    │◀─────── 面试安排/反馈 ───────────────────────────────────────────────│
    │                                       │                                │
```

---

### 敏感字段处理规则

| 字段 | 原始值 | 脱敏后 | 规则 |
|------|--------|--------|------|
| phone | 13812345678 | 138****5678 | 中间4位打码 |
| email | a@b.com | a***@b.com | @前保留1位 |
| name | 张三 | 张* | 末字打码 |
| salary | 45万 | 40-50万 | 范围模糊化 |

**脱敏策略：**
- 信息流向甲方时，猎头敏感信息脱敏
- 信息流回猎头时，甲方敏感信息脱敏
- 中介平台保留原始数据（用于纠纷追溯）

---

### 猎头场景规则配置

```json
[
  {
    "id": "headhunt_001",
    "name": "匹配度低于60%自动拒绝",
    "priority": 10,
    "conditions": [
      {"field": "intent", "op": "==", "value": "job_match"},
      {"field": "payload.match_score", "op": "<", "value": 0.6}
    ],
    "action": "auto_reject"
  },
  {
    "id": "headhunt_002",
    "name": "高管职位需人工审批",
    "priority": 20,
    "conditions": [
      {"field": "intent", "op": "==", "value": "job_match"},
      {"field": "payload.jd_id.level", "op": "in", "value": ["C-Level", "VP"]}
    ],
    "action": "manual_review"
  },
  {
    "id": "headhunt_003",
    "name": "快速通道：小额普通职位自动通过",
    "priority": 5,
    "conditions": [
      {"field": "intent", "op": "==", "value": "job_match"},
      {"field": "payload.jd_id.level", "op": "in", "value": ["P5", "P6", "中级"]}
    ],
    "action": "auto_approve"
  }
]
```

---

### 下一步：数据持久化

需要支持：
- JD / Candidate 的存储和查询
- 匹配记录的历史追溯
- 审批状态的持久化

建议用 SQLite + SQLAlchemy 或直接用 JSON 文件。

| 阶段 | 内容 | 代码量 |
|------|------|--------|
| P0 | 请求接入 + 规则命中 + 自动通过/拒绝 | ~150行 |
| P1 | 人工审批台 + 审批记录 | ~100行 |
| P2 | 路由分发 + 响应回传 | ~100行 |
| P3 | 规则管理界面 + webhook 回调 | ~150行 |

---

## 借鉴设计：NeverLand 游戏 Skill 架构

参考自：https://neverland.coze.com/skill.md

### 核心借鉴点

#### 1. 统一操作接口
```json
// NeverLand 风格
{"action_type": "harvest", "crop_type": "...", "positions": [...]}

// 中介平台借鉴
{"action_type": "route_request", "source": "猎头_skill", "intent": "职位匹配", "payload": {...}}
```

所有 Skill 接入统一入口，规则引擎像"游戏逻辑"一样处理，而非散落 if-else。

---

#### 2. 资源配额系统 → 接入方限流 + 商业化

| NeverLand | 中介平台场景 |
|-----------|-------------|
| 体力限制频率 | 每小时最多 N 个请求 |
| 每日配额 | 每天免费额度，超量收费 |
| 体力不够只能等 | 配额用完请求被拒绝或排队 |

差异化 SLA + 商业化基础。

---

#### 3. 配置驱动 → 规则热更新

```bash
GET /api/game/config    # 纯数据（作物、动物、建筑配置）
POST .../action         # 纯逻辑（操作执行）
```

```bash
GET /api/rules          # 返回当前规则配置（JSON）
POST /api/request       # 请求经过规则引擎处理
```

新增规则不需要改代码，只在配置中心添加。

---

#### 4. 状态 API + 建议操作

NeverLand status API 返回推荐操作，降低 AI 决策难度。

中介平台审批台可借鉴：
```json
GET /api/pending?source=猎头_skill
→ 返回:
[
  {
    "request": {...},
    "suggestion": "自动通过",
    "confidence": 0.95,
    "matchedRule": "rule_001"
  }
]
```

帮助审批者快速决策。

---

#### 5. 错误码体系 → 标准化响应

```json
// NeverLand
{"error": "INSUFFICIENT_RESOURCES", "message": "...", "action": "wait_for_regen"}

// 中介平台
{"error": "RULE_MISMATCH", "message": "请求不符合当前规则", "action": "contact_admin"}
```

接入方可根据错误码做自己的错误处理。

---

### 设计思想总结

**核心原则：数据（规则/配置）与逻辑（处理引擎）分离**

| 设计 | 用在中介平台的哪里 |
|------|-------------------|
| 统一操作接口 | 所有 Skill 接入格式统一 |
| 资源配额系统 | 接入方限流 + 商业化 |
| 配置驱动 | 规则热更新，不改代码 |
| 状态 + 建议 | 审批台辅助决策 |
| 错误码体系 | 标准化接入方错误处理 |

---

### 扩展性对比

```
NeverLand: 46作物 + 40动物 + 30建筑 + 31特殊物品
          → 只需在 config API 添加条目，前端无需改动

中介平台: 规则数量 + 接入方数量 + Intent 类型
          → 只需在配置中心添加，前端无需改动
```

这是典型的**数据驱动架构**，核心引擎与内容完全解耦。

---

# Skill Link 协议设计

## 1. 概述

Skill Link 是中介平台的核心协议，设计用于让 Agent 通过 `skill_name` 直接调用技能端点，无需构造复杂的 JSON 请求体。

### 1.1 设计目标

- **简化调用**: Agent 只需知道 `skill_name` 和 `action`，通过路径直接调用
- **标准化响应**: 所有响应统一格式 `{status, code, data, message}`
- **内置技能**: 平台预置常用技能，开箱即用
- **错误可控**: 明确的错误码体系，便于 Agent 处理异常

### 1.2 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent Client                           │
└─────────────────┬─────────────────────────────────────────┘
                  │ HTTP Request /skill/{skill_name}/{action}
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                    api_server.py                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Auth      │→ │ Rate Limit  │→ │  Skill Dispatcher   │ │
│  │  (Token)    │  │             │  │                     │ │
│  └─────────────┘  └─────────────┘  └──────────┬──────────┘ │
│                                                  │            │
│  ┌──────────────────────────────────────────────▼──────────┐ │
│  │              Skill Handlers                          │ │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────────────┐ │ │
│  │  │ 猎头_skill │ │ 甲方_skill │ │ 平台_skill          │ │ │
│  │  └────────────┘ └────────────┘ └────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐   │
│  │               MediatorAPIP3                          │   │
│  │  RuleEngine │ ApprovalDesk │ Router │ Managers...    │   │
│  └───────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 路径格式

### 2.1 标准路径

```
GET/POST /skill/{skill_name}/{action}[?params...]
```

| 组成部分 | 说明 | 示例 |
|---------|------|------|
| `skill` | 固定前缀，表示技能调用 | `/skill/` |
| `{skill_name}` | 技能名称 | `猎头_skill` |
| `{action}` | 动作名称 | `submit_jd` |
| Query Params | 可选查询参数 | `?request_id=xxx` |

### 2.2 调用示例

```bash
# 猎头提交 JD
POST /skill/猎头_skill/submit_jd
Content-Type: application/json
Authorization: Bearer {token}

{
  "jd_title": "高级前端工程师",
  "jd_level": "P7",
  "salary_range": "40-60K",
  "requirements": ["React", "TypeScript"]
}

# 猎头提交候选人
POST /skill/猎头_skill/submit_candidate
{
  "candidate_name": "张三",
  "experience": "5年",
  "skills": ["React", "Node.js"],
  "expected_salary": "50K"
}

# 猎头提交匹配请求
POST /skill/猎头_skill/submit_match
{
  "jd_id": "jd_abc123",
  "candidate_id": "cand_xyz789"
}

# 甲方获取待匹配列表
GET /skill/甲方_skill/get_pending_matches

# 甲方回复面试邀请
POST /skill/甲方_skill/reply_interview
{
  "match_id": "match_123",
  "decision": "accept",
  "interview_time": "2026-06-15 14:00"
}

# 平台审批
POST /skill/平台_skill/approve
{
  "request_id": "req_abc123"
}

# 平台获取规则
GET /skill/平台_skill/get_rules
```

---

## 3. 统一响应格式

### 3.1 响应结构

```json
{
  "status": "success|error|pending",
  "code": "MATCH_SUBMITTED|REQUEST_APPROVED|...",
  "data": { ... },
  "message": "中文说明"
}
```

| 字段 | 类型 | 说明 |
|-----|------|------|
| `status` | string | 结果状态: `success`=成功, `error`=错误, `pending`=待审批 |
| `code` | string | 结果码，用于 Agent 判断处理结果 |
| `data` | object | 业务数据，结构因 action 而异 |
| `message` | string | 人类可读的中文说明 |

### 3.2 响应示例

**成功响应**
```json
{
  "status": "success",
  "code": "MATCH_SUBMITTED",
  "data": {
    "match_id": "match_abc123",
    "jd_id": "jd_xxx",
    "candidate_id": "cand_yyy",
    "status": "pending",
    "created_at": "2026-05-31T10:30:00Z"
  },
  "message": "匹配请求已提交，等待甲方确认"
}
```

**错误响应**
```json
{
  "status": "error",
  "code": "ERR_MISSING_PARAM",
  "data": null,
  "message": "缺少必填参数: jd_id"
}
```

**待审批响应**
```json
{
  "status": "pending",
  "code": "REQUEST_PENDING",
  "data": {
    "request_id": "req_abc123",
    "suggestion": "建议通过（小额）",
    "confidence": 0.8
  },
  "message": "请求已提交，需平台管理员审批"
}
```

---

## 4. 错误码体系

### 4.1 错误码列表

| 错误码 | 说明 | HTTP Status | 适用场景 |
|--------|------|-------------|---------|
| `ERR_INVALID_SKILL` | 技能不存在 | 404 | 调用未注册的 skill_name |
| `ERR_INVALID_ACTION` | 动作不存在 | 404 | 调用未注册 action |
| `ERR_MISSING_PARAM` | 缺少参数 | 400 | 必填参数缺失 |
| `ERR_INVALID_PARAM` | 参数无效 | 400 | 参数格式/值不合法 |
| `ERR_QUOTA_EXCEEDED` | 配额耗尽 | 429 | 超出每小时配额限制 |
| `ERR_UNAUTHORIZED` | 未授权 | 401 | Token 无效或过期 |
| `ERR_FORBIDDEN` | 权限不足 | 403 | 角色权限不够 |
| `ERR_NOT_FOUND` | 资源不存在 | 404 | 请求/匹配/路由记录不存在 |
| `ERR_ALREADY_EXISTS` | 资源已存在 | 409 | 重复提交 |
| `ERR_INTERNAL` | 内部错误 | 500 | 服务器内部错误 |

### 4.2 业务状态码

| 状态码 | 说明 | 触发条件 |
|--------|------|---------|
| `REQUEST_SUBMITTED` | 请求已提交 | submit_request 成功 |
| `REQUEST_APPROVED` | 请求已批准 | approve 成功 |
| `REQUEST_REJECTED` | 请求已拒绝 | reject 成功 |
| `MATCH_SUBMITTED` | 匹配已提交 | submit_match 成功 |
| `MATCH_ACCEPTED` | 匹配已接受 | reply_interview 接受 |
| `MATCH_REJECTED` | 匹配已拒绝 | reply_interview 拒绝 |
| `INTERVIEW_SCHEDULED` | 面试已安排 | interview_time 确认 |
| `JD_CLOSED` | JD 已关闭 | close_jd 成功 |
| `REQUEST_PENDING` | 请求待审批 | 进入人工审批队列 |
| `QUOTA_UPDATED` | 配额已更新 | update_quota 成功 |
| `RULES_FETCHED` | 规则已获取 | get_rules 成功 |

---

## 5. 内置技能定义

### 5.1 猎头_skill

猎头（Recruiter）使用的技能集。

| Action | 说明 | 输入参数 | 输出 data |
|--------|------|---------|---------|
| `submit_jd` | 提交职位描述 | `jd_title`, `jd_level`, `salary_range`, `requirements[]` | `{jd_id, status}` |
| `submit_candidate` | 提交候选人 | `candidate_name`, `experience`, `skills[]`, `expected_salary` | `{candidate_id, status}` |
| `submit_match` | 提交匹配请求 | `jd_id`, `candidate_id` | `{match_id, status, created_at}` |
| `get_match_status` | 查询匹配状态 | `match_id` (query) | `{match_id, jd_id, candidate_id, status, decision}` |

**请求示例**
```bash
POST /skill/猎头_skill/submit_match
{
  "jd_id": "jd_abc123",
  "candidate_id": "cand_xyz789"
}
```

**响应示例**
```json
{
  "status": "success",
  "code": "MATCH_SUBMITTED",
  "data": {
    "match_id": "match_xxx",
    "jd_id": "jd_abc123",
    "candidate_id": "cand_xyz789",
    "status": "pending",
    "created_at": "2026-05-31T10:30:00Z"
  },
  "message": "匹配请求已提交，等待甲方确认"
}
```

### 5.2 甲方_skill

甲方企业（Client Company）使用的技能集。

| Action | 说明 | 输入参数 | 输出 data |
|--------|------|---------|---------|
| `get_pending_matches` | 获取待处理匹配列表 | 无 | `{matches: [{match_id, jd_title, candidate_name, submitted_at}]}` |
| `reply_interview` | 回复面试邀请 | `match_id`, `decision` (accept/reject), `interview_time` (可选) | `{match_id, status, reply_time}` |
| `close_jd` | 关闭职位 | `jd_id` (query) | `{jd_id, status, closed_at}` |

**请求示例**
```bash
GET /skill/甲方_skill/get_pending_matches
```

**响应示例**
```json
{
  "status": "success",
  "code": "MATCH_LIST_FETCHED",
  "data": {
    "matches": [
      {
        "match_id": "match_xxx",
        "jd_title": "高级前端工程师",
        "jd_level": "P7",
        "candidate_name": "张三",
        "submitted_at": "2026-05-31T10:30:00Z"
      }
    ],
    "total": 1
  },
  "message": "获取到 1 条待处理匹配"
}
```

### 5.3 平台_skill

平台管理员使用的技能集。

| Action | 说明 | 输入参数 | 输出 data |
|--------|------|---------|---------|
| `approve` | 审批通过 | `request_id` | `{request_id, status, approved_at}` |
| `reject` | 审批拒绝 | `request_id`, `reason` (可选) | `{request_id, status, rejected_at}` |
| `get_rules` | 获取规则列表 | 无 | `{rules: [{id, name, priority, enabled}]}` |
| `update_quota` | 更新配额 | `source`, `hourly_limit` | `{source, hourly_limit, remaining}` |
| `get_pending_requests` | 获取待审批请求 | 无 | `{requests: [...]}` |

**请求示例**
```bash
POST /skill/平台_skill/approve
{
  "request_id": "req_abc123"
}
```

**响应示例**
```json
{
  "status": "success",
  "code": "REQUEST_APPROVED",
  "data": {
    "request_id": "req_abc123",
    "status": "approved",
    "approved_at": "2026-05-31T11:00:00Z"
  },
  "message": "请求已批准"
}
```

---

## 6. api_server.py 需添加的端点

### 6.1 Skill Link 主入口（统一调度）

```python
# POST /skill/{skill_name}/{action}
@app.post("/skill/{skill_name}/{action}", dependencies=[Depends(get_current_token)])
async def skill_action_post(skill_name: str, action: str, request: Request):
    """Skill Link POST 统一入口"""
    # 参数解析 + 调度到对应 Skill Handler

# GET /skill/{skill_name}/{action}
@app.get("/skill/{skill_name}/{action}", dependencies=[Depends(get_current_token)])
async def skill_action_get(skill_name: str, action: str, request: Request):
    """Skill Link GET 统一入口"""
```

### 6.2 猎头_skill 端点

```python
@app.post("/skill/猎头_skill/submit_jd", dependencies=[Depends(get_current_token)])
def submit_jd(body: JDInput):
    """提交职位描述"""

@app.post("/skill/猎头_skill/submit_candidate", dependencies=[Depends(get_current_token)])
def submit_candidate(body: CandidateInput):
    """提交候选人"""

@app.post("/skill/猎头_skill/submit_match", dependencies=[Depends(get_current_token)])
def submit_match(body: MatchInput):
    """提交匹配请求"""

@app.get("/skill/猎头_skill/get_match_status", dependencies=[Depends(get_current_token)])
def get_match_status(match_id: str = Query(...)):
    """查询匹配状态"""
```

### 6.3 甲方_skill 端点

```python
@app.get("/skill/甲方_skill/get_pending_matches", dependencies=[Depends(get_current_token)])
def get_pending_matches():
    """获取待处理匹配列表"""

@app.post("/skill/甲方_skill/reply_interview", dependencies=[Depends(get_current_token)])
def reply_interview(body: InterviewReplyInput):
    """回复面试邀请"""

@app.post("/skill/甲方_skill/close_jd", dependencies=[Depends(get_current_token)])
def close_jd(jd_id: str = Query(...)):
    """关闭职位"""
```

### 6.4 平台_skill 端点

```python
@app.post("/skill/平台_skill/approve", dependencies=[Depends(get_current_token)])
def platform_approve(body: ApproveInput):
    """平台审批通过"""

@app.post("/skill/平台_skill/reject", dependencies=[Depends(get_current_token)])
def platform_reject(body: RejectInput):
    """平台审批拒绝"""

@app.get("/skill/平台_skill/get_rules", dependencies=[Depends(get_current_token)])
def platform_get_rules():
    """获取平台规则"""

@app.post("/skill/平台_skill/update_quota", dependencies=[Depends(get_current_token)])
def platform_update_quota(body: QuotaInput):
    """更新配额"""

@app.get("/skill/平台_skill/get_pending_requests", dependencies=[Depends(get_current_token)])
def platform_get_pending_requests():
    """获取待审批请求"""
```

---

## 7. 实现优先级建议

### 7.1 Phase 1: 核心框架 (P0)

**目标**: 建立 Skill Link 基础框架，统一响应格式

| 优先级 | 任务 | 工作量 |
|--------|------|--------|
| P0-1 | 创建 SkillLinkResponse 统一响应模型 | 小 |
| P0-2 | 创建 SkillDispatcher 调度器 | 中 |
| P0-3 | 实现错误码常量和异常类 | 小 |
| P0-4 | 添加 `/skill/{skill_name}/{action}` 主入口 | 中 |
| P0-5 | 编写统一响应中间件 | 小 |

### 7.2 Phase 2: 内置技能实现 (P1)

**目标**: 实现三大内置技能

| 优先级 | 任务 | 工作量 |
|--------|------|--------|
| P1-1 | 实现猎头_skill (submit_jd, submit_candidate, submit_match, get_match_status) | 中 |
| P1-2 | 实现甲方_skill (get_pending_matches, reply_interview, close_jd) | 中 |
| P1-3 | 实现平台_skill (approve, reject, get_rules, update_quota) | 中 |
| P1-4 | 添加配额检查和等待队列集成 | 中 |

### 7.3 Phase 3: 增强功能 (P2)

**目标**: 增强可用性和可观测性

| 优先级 | 任务 | 工作量 |
|--------|------|--------|
| P2-1 | 添加 Skill Link OpenAPI 文档 | 小 |
| P2-2 | 添加调用链路追踪 (request_id 传递) | 中 |
| P2-3 | 添加 Skill 调用指标埋点 | 小 |
| P2-4 | 支持 Webhook 事件触发 Skill | 中 |

### 7.4 Phase 4: 高级功能 (P3)

**目标**: 支持复杂业务场景

| 优先级 | 任务 | 工作量 |
|--------|------|--------|
| P3-1 | 支持 Skill 编排 (多个 Skill 组合调用) | 大 |
| P3-2 | 支持 Skill 回调 (异步响应) | 中 |
| P3-3 | 支持 Skill 限流和熔断 | 中 |
| P3-4 | 添加 Skill 市场发现机制 | 大 |

---

## 8. 关键设计决策

### 8.1 为什么用路径而不是 Query Parameter？

路径 `/skill/猎头_skill/submit_match` 比查询 `/skill?skill=猎头_skill&action=submit_match` 更符合 RESTful 规范，且：
- 更好的可读性
- 便于 API Gateway 路由配置
- 便于 OpenAPI 文档自动生成

### 8.2 为什么统一响应格式？

Agent 需要一种确定性的方式判断调用结果：
- `status`: 让 Agent 快速判断是成功/失败/需人工介入
- `code`: 精确判断业务结果类型
- `message`: 给人类可读的解释
- `data`: 具体的业务数据

### 8.3 为什么需要 Skill 抽象？

当前系统已经通过 `source`/`target` 区分请求来源，但：
- Skill 抽象提供更明确的语义
- 便于添加 Skill 级别的配额和权限控制
- 便于扩展和支持 Skill 编排

---

## 9. 后续扩展

### 9.1 Skill 发现机制

未来可添加 `/skills` 端点列出所有可用 Skill：

```json
GET /skills

{
  "skills": [
    {"name": "猎头_skill", "description": "猎头招聘技能", "actions": ["submit_jd", ...]},
    {"name": "甲方_skill", "description": "甲方企业技能", "actions": ["get_pending_matches", ...]},
    {"name": "平台_skill", "description": "平台管理技能", "actions": ["approve", ...]}
  ]
}
```

### 9.2 Skill 编排

支持多个 Skill 组合调用：

```json
POST /skill/chain
{
  "steps": [
    {"skill": "猎头_skill", "action": "submit_match"},
    {"skill": "甲方_skill", "action": "reply_interview"},
    {"skill": "平台_skill", "action": "approve"}
  ]
}
```

---

## 10. 附录

### 10.1 相关文件

- `api_server.py`: FastAPI HTTP 层
- `p1_p2.py`: 核心业务逻辑
- `auth.py`: API Key 认证

### 10.2 依赖版本

- Python 3.10+
- FastAPI 0.100+
- Pydantic 2.0+