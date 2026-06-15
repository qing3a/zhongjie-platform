# 中介 API 平台 - API 文档

**版本**: 1.0.0
**协议**: Skill Link
**Base URL**: `http://localhost:8000`

---

## 目录

- [快速开始](#快速开始)
- [认证](#认证)
- [Skill Link 协议](#skill-link-协议)
- [端点列表](#端点列表)
- [错误码参考](#错误码参考)
- [分页](#分页)
- [幂等性](#幂等性)
- [限流](#限流)

---

## 快速开始

### 1. 获取 Token

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_app",
    "role": "requester",
    "tenant_id": "default"
  }'
```

**响应**:
```json
{
  "key_id": "key_abc123",
  "secret": "sec_xyz789...",
  "expires_at": "2027-05-31T00:00:00Z"
}
```

### 2. 调用 Skill API

```bash
curl -X POST http://localhost:8000/skill/猎头_skill/submit_jd \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jd_title": "高级Python工程师",
    "jd_level": "P6",
    "salary_range": "30-50K",
    "requirements": ["Python", "FastAPI", "SQL"]
  }'
```

---

## 认证

所有 API（除 `/api/auth/token` 外）需要通过 `Authorization` header 传递 Token：

```
Authorization: Bearer YOUR_TOKEN
```

Token 通过 `POST /api/auth/token` 生成，有效期默认 365 天。

---

## Skill Link 协议

### 响应格式

所有 Skill Link 端点返回统一响应格式：

```json
{
  "status": "success|error|pending",
  "code": "错误码或业务码",
  "data": {...},
  "message": "说明文字",
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-05-31T10:30:00Z",
    "version": "1.0",
    "quota_warning": "配额使用已达 85%"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `success` 成功 / `error` 错误 / `pending` 待处理 |
| code | string | 业务码或错误码 |
| data | any | 业务数据 |
| message | string | 人类可读说明 |
| meta | object | 元数据（含 request_id, timestamp 等） |

---

## 端点列表

### Skill API（统一入口）

#### POST /skill/{skill_name}/{action}

执行 Skill 动作（POST 方式）。

**路径参数**:
- `skill_name`: 技能名称
- `action`: 动作名称

**Headers**:
- `Authorization: Bearer TOKEN` (必填)
- `X-Idempotency-Key: KEY` (可选，幂等性Key)

**请求体示例**:
```json
{
  "jd_title": "高级Python工程师",
  "jd_level": "P6",
  "salary_range": "30-50K",
  "requirements": ["Python", "FastAPI", "SQL"]
}
```

**响应示例**:
```json
{
  "status": "success",
  "code": "JD_SUBMITTED",
  "data": {
    "jd_id": "jd_abc123",
    "status": "active"
  },
  "message": "JD '高级Python工程师' 已提交",
  "meta": {
    "request_id": "req_xyz789",
    "timestamp": "2026-05-31T10:30:00Z",
    "version": "1.0"
  }
}
```

---

#### GET /skill/{skill_name}/{action}

查询 Skill 数据（GET 方式）。

**路径参数**:
- `skill_name`: 技能名称
- `action`: 动作名称

**查询参数**:
- `page`: 页码 (默认 1)
- `page_size`: 每页条数 (默认 20)
- 其他业务参数

**响应示例**:
```json
{
  "status": "success",
  "code": "MATCH_LIST_FETCHED",
  "data": {
    "items": [
      {
        "match_id": "match_123",
        "jd_title": "高级Python工程师",
        "candidate_name": "张*"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    }
  },
  "message": "获取到 1 条待处理匹配"
}
```

---

### 猎头_skill

管理 JD、候选人、匹配请求。

#### submit_jd - 提交职位

**请求**:
```json
{
  "jd_title": "高级Python工程师",
  "jd_level": "P6",
  "salary_range": "30-50K",
  "requirements": ["Python", "FastAPI", "SQL"]
}
```

**响应**:
```json
{
  "status": "success",
  "code": "JD_SUBMITTED",
  "data": {
    "jd_id": "jd_abc123",
    "status": "active"
  },
  "message": "JD '高级Python工程师' 已提交"
}
```

#### submit_candidate - 提交候选人

**请求**:
```json
{
  "candidate_name": "张三",
  "experience": "5年Python开发经验",
  "skills": ["Python", "Django", "PostgreSQL"],
  "expected_salary": "40K",
  "phone": "13812345678",
  "email": "zhangsan@example.com"
}
```

**响应**:
```json
{
  "status": "success",
  "code": "CANDIDATE_SUBMITTED",
  "data": {
    "candidate_id": "cand_xyz789",
    "status": "active"
  },
  "message": "候选人 '张*' 已提交"
}
```

> 注意：敏感字段（phone, email, name）会自动脱敏

#### submit_match - 提交匹配请求

**请求**:
```json
{
  "jd_id": "jd_abc123",
  "candidate_id": "cand_xyz789"
}
```

**响应**:
```json
{
  "status": "pending",
  "code": "REQUEST_PENDING",
  "data": {
    "match_id": "match_123",
    "jd_id": "jd_abc123",
    "candidate_id": "cand_xyz789",
    "status": "pending"
  },
  "message": "匹配请求已提交，等待甲方确认"
}
```

#### get_match_status - 查询匹配状态

**查询参数**: `match_id` (必填)

**响应**:
```json
{
  "status": "success",
  "code": "MATCH_STATUS_FETCHED",
  "data": {
    "match_id": "match_123",
    "jd_id": "jd_abc123",
    "candidate_id": "cand_xyz789",
    "status": "pending"
  },
  "message": "匹配状态已获取"
}
```

---

### 甲方_skill

甲方端管理。

#### get_pending_matches - 获取待处理匹配

**查询参数**:
- `page`: 页码 (默认 1)
- `page_size`: 每页条数 (默认 20)

**响应**:
```json
{
  "status": "success",
  "code": "MATCH_LIST_FETCHED",
  "data": {
    "items": [
      {
        "match_id": "match_123",
        "jd_title": "高级Python工程师",
        "jd_level": "P6",
        "candidate_name": "张*",
        "submitted_at": "2026-05-31T10:30:00Z"
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    }
  },
  "message": "获取到 1 条待处理匹配"
}
```

#### reply_interview - 回复面试邀请

**请求**:
```json
{
  "match_id": "match_123",
  "decision": "accept"
}
```

> `decision` 可选值: `accept` / `reject`

**响应**:
```json
{
  "status": "success",
  "code": "MATCH_ACCEPTED",
  "data": {
    "match_id": "match_123",
    "status": "accepted",
    "reply_time": "2026-05-31T11:00:00Z"
  },
  "message": "面试邀请已接受"
}
```

#### close_jd - 关闭职位

**请求**:
```json
{
  "jd_id": "jd_abc123"
}
```

**响应**:
```json
{
  "status": "success",
  "code": "JD_CLOSED",
  "data": {
    "jd_id": "jd_abc123",
    "status": "closed",
    "closed_at": "2026-05-31T11:00:00Z"
  },
  "message": "JD '高级Python工程师' 已关闭"
}
```

---

### 平台_skill

平台管理功能。

#### approve - 审批通过

**请求**:
```json
{
  "request_id": "req_abc123",
  "decided_by": "admin",
  "comment": "同意"
}
```

**响应**:
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

#### reject - 审批拒绝

**请求**:
```json
{
  "request_id": "req_abc123",
  "reason": "不符合要求",
  "decided_by": "admin"
}
```

**响应**:
```json
{
  "status": "success",
  "code": "REQUEST_REJECTED",
  "data": {
    "request_id": "req_abc123",
    "status": "rejected",
    "rejected_at": "2026-05-31T11:00:00Z"
  },
  "message": "请求已拒绝"
}
```

#### get_rules - 获取规则列表

**查询参数**:
- `page`: 页码 (默认 1)
- `page_size`: 每页条数 (默认 20)

**响应**:
```json
{
  "status": "success",
  "code": "RULES_FETCHED",
  "data": {
    "items": [
      {
        "id": "rule_001",
        "name": "高额自动审批",
        "conditions": [{"field": "amount", "op": "lt", "value": 1000}],
        "action": "auto_approve",
        "priority": 10,
        "enabled": true
      }
    ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 1,
      "total_pages": 1
    }
  },
  "message": "获取到 1 条规则"
}
```

#### update_quota - 更新配额

**请求**:
```json
{
  "source": "client_abc",
  "hourly_limit": 1000
}
```

**响应**:
```json
{
  "status": "success",
  "code": "QUOTA_UPDATED",
  "data": {
    "source": "client_abc",
    "hourly_limit": 1000
  },
  "message": "配额已更新: client_abc -> 1000/小时"
}
```

#### get_quota - 查询配额

**查询参数**: `source` (必填)

**响应**:
```json
{
  "status": "success",
  "code": "QUOTA_FETCHED",
  "data": {
    "source": "client_abc",
    "hourly_limit": 1000,
    "used": 150,
    "remaining": 850,
    "reset_at": "2026-05-31T11:00:00Z",
    "waiting_count": 0
  },
  "message": "配额查询成功: client_abc"
}
```

#### get_pending_requests - 获取待审批请求

**查询参数**:
- `page`: 页码 (默认 1)
- `page_size`: 每页条数 (默认 20)

**响应**:
```json
{
  "status": "success",
  "code": "REQUEST_PENDING",
  "data": {
    "items": [],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 0,
      "total_pages": 0
    }
  },
  "message": "获取到 0 条待审批请求"
}
```

#### export_data - 数据导出

**查询参数**:
- `type`: 导出类型 - `approvals` | `routes` | `audit` | `billing` (必填)
- `format`: 导出格式 - `json` | `csv` (默认 json)
- `start_date`: 开始日期 YYYY-MM-DD (可选)
- `end_date`: 结束日期 YYYY-MM-DD (可选)
- `page`: 页码 (默认 1)
- `page_size`: 每页条数 (默认 1000)

**响应 (JSON)**:
```json
{
  "status": "success",
  "code": "DATA_EXPORTED",
  "data": {
    "format": "json",
    "data": [],
    "page": 1,
    "page_size": 1000,
    "total": 0,
    "total_pages": 0
  },
  "message": "导出 approvals 数据成功，共 0 条"
}
```

---

### 批量操作 API

#### POST /api/batch

批量执行多个 Skill Action，减少网络开销。

**请求**:
```json
{
  "requests": [
    {
      "skill": "猎头_skill",
      "action": "submit_jd",
      "params": {
        "jd_title": "职位1",
        "jd_level": "P6"
      }
    },
    {
      "skill": "猎头_skill",
      "action": "submit_candidate",
      "params": {
        "candidate_name": "张三"
      }
    }
  ]
}
```

**响应**:
```json
{
  "status": "success",
  "code": "BATCH_COMPLETED",
  "data": {
    "results": [
      {
        "index": 0,
        "response": {"status": "success", "code": "JD_SUBMITTED", ...}
      },
      {
        "index": 1,
        "response": {"status": "success", "code": "CANDIDATE_SUBMITTED", ...}
      }
    ],
    "success_count": 2,
    "failure_count": 0
  },
  "message": "批量操作完成: 2成功, 0失败"
}
```

---

### 工作流 API

#### POST /skill/{skill_name}/execute_workflow

按顺序执行多个 Skill Action。

**请求**:
```json
{
  "workflow": [
    {
      "skill": "猎头_skill",
      "action": "submit_jd",
      "params": {"jd_title": "职位1"}
    },
    {
      "skill": "猎头_skill",
      "action": "submit_candidate",
      "params": {"candidate_name": "张三"}
    }
  ]
}
```

**响应**:
```json
{
  "status": "success",
  "code": "WORKFLOW_COMPLETED",
  "data": {
    "steps": [
      {
        "index": 0,
        "skill": "猎头_skill",
        "action": "submit_jd",
        "result": {"status": "success", ...},
        "success": true,
        "duration_ms": 120
      },
      {
        "index": 1,
        "skill": "猎头_skill",
        "action": "submit_candidate",
        "result": {"status": "success", ...},
        "success": true,
        "duration_ms": 85
      }
    ],
    "failed_steps": [],
    "total_duration_ms": 205
  },
  "message": "工作流执行完成: 2成功, 0失败"
}
```

---

### 基础 API

#### POST /api/auth/token - 生成 Token

**请求**:
```json
{
  "name": "my_app",
  "role": "requester",
  "tenant_id": "default",
  "days_valid": 365
}
```

**响应**:
```json
{
  "key_id": "key_abc123",
  "secret": "sec_xyz789...",
  "expires_at": "2027-05-31T00:00:00Z"
}
```

#### POST /api/request - 提交请求

**请求**:
```json
{
  "source": "client_abc",
  "target": "platform",
  "intent": "submit_jd",
  "payload": {"jd_title": "职位1"},
  "metadata": {}
}
```

**响应**:
```json
{
  "request": {"id": "req_123", "status": "pending"},
  "result": {"action": "manual_review", "rule_id": "rule_001"}
}
```

#### GET /api/pending - 待审批列表

**响应**:
```json
[
  {
    "request": {"id": "req_123", "source": "client_abc", "intent": "submit_jd"},
    "suggestion": {"action": "manual_review", "reason": "金额超过阈值"}
  }
]
```

#### POST /api/approval/{request_id}/approve - 审批通过

**请求**:
```json
{
  "decided_by": "admin",
  "comment": "同意"
}
```

**响应**:
```json
{
  "request": {"id": "req_123", "status": "approved"},
  "approved_at": "2026-05-31T11:00:00Z"
}
```

#### POST /api/approval/{request_id}/reject - 审批拒绝

**请求**:
```json
{
  "decided_by": "admin",
  "comment": "不符合要求"
}
```

#### GET /api/approvals - 审批历史

**查询参数**: `request_id` (可选)

#### POST /api/route/{request_id} - 路由分发

**请求**:
```json
{
  "forwarded_payload": {}
}
```

#### GET /api/routes - 路由列表

**查询参数**: `request_id` (可选)

#### POST /api/route/{route_id}/reply - 接收回复

**请求**:
```json
{
  "reply_payload": {}
}
```

#### GET /api/rules - 规则列表

#### POST /api/rules - 添加规则

**请求**:
```json
{
  "id": "rule_001",
  "name": "高额自动审批",
  "conditions": [{"field": "amount", "op": "lt", "value": 1000}],
  "action": "auto_approve",
  "priority": 10,
  "enabled": true
}
```

#### PUT /api/rules/{rule_id} - 更新规则

#### DELETE /api/rules/{rule_id} - 删除规则

#### GET /api/quota/{source} - 查询配额

#### PUT /api/quota/{source} - 设置配额

**请求**:
```json
{
  "hourly_limit": 1000
}
```

#### GET /api/waiting - 等待队列

#### POST /api/webhooks - 注册 Webhook

**请求**:
```json
{
  "event": "request_approved",
  "url": "https://example.com/webhook"
}
```

#### GET /api/webhooks - Webhook 列表

#### DELETE /api/webhooks/{webhook_id} - 注销 Webhook

#### POST /api/callbacks/register - 注册回调

**请求**:
```json
{
  "skill_name": "甲方_skill",
  "url": "https://example.com/callback",
  "events": ["match_created", "interview_scheduled"]
}
```

#### GET /api/callbacks - 回调列表

#### DELETE /api/callbacks/{callback_id} - 删除回调

#### GET /api/billing - 计费汇总

#### GET /api/audit - 审计日志

**查询参数**:
- `action`: 动作类型 (可选)
- `object_type`: 对象类型 (可选)
- `limit`: 返回条数 (默认 100)

#### GET /api/security - 安全事件

---

### 文档端点

#### GET /api/docs/schema

返回完整的 OpenAPI JSON Schema，包含所有端点的详细描述、请求示例、响应示例、错误码说明。

**响应**: OpenAPI schema JSON

#### GET /api/docs/skills

返回 Skill Link 协议的机器可读描述。

**响应**:
```json
{
  "protocol": "Skill Link",
  "version": "1.0",
  "description": "统一接口规范，让 Agent 更容易理解和调用平台能力",
  "response_format": {...},
  "error_codes": {...},
  "skills": {...},
  "pagination": {...},
  "idempotency": {...},
  "rate_limiting": {...}
}
```

---

### 健康检查

#### GET /health/live

进程存活检查。

**响应**:
```json
{
  "status": "ok",
  "timestamp": "2026-05-31T10:30:00Z"
}
```

#### GET /health/ready

依赖就绪检查。

**响应**:
```json
{
  "status": "ok",
  "checks": {
    "data_directory": {"status": "ok", "path": "data"},
    "disk_space": {"status": "ok", "free_bytes": 500000000000}
  },
  "timestamp": "2026-05-31T10:30:00Z"
}
```

---

## 错误码参考

### 系统错误 (5xx)

| 错误码 | HTTP状态 | 说明 | 可重试 |
|--------|----------|------|--------|
| ERR_INTERNAL | 500 | 系统内部错误 | 是 |
| ERR_INVALID_SKILL | 404 | 无效的技能名称 | 否 |
| ERR_INVALID_ACTION | 404 | 无效的动作名称 | 否 |

### 请求错误 (4xx)

| 错误码 | HTTP状态 | 说明 | 可重试 |
|--------|----------|------|--------|
| ERR_MISSING_PARAM | 400 | 缺少必填参数 | 否 |
| ERR_INVALID_PARAM | 400 | 无效的参数值 | 否 |
| ERR_QUOTA_EXCEEDED | 429 | 配额超限 | 是 |
| ERR_UNAUTHORIZED | 401 | 未授权访问 | 否 |
| ERR_FORBIDDEN | 403 | 权限不足 | 否 |
| ERR_NOT_FOUND | 404 | 资源不存在 | 否 |
| ERR_ALREADY_EXISTS | 409 | 资源已存在 | 否 |

### 业务状态码

| 状态码 | 说明 |
|--------|------|
| REQUEST_SUBMITTED | 请求已提交 |
| REQUEST_APPROVED | 请求已批准 |
| REQUEST_REJECTED | 请求已拒绝 |
| REQUEST_PENDING | 请求待审批 |
| JD_SUBMITTED | JD 已提交 |
| JD_CLOSED | JD 已关闭 |
| CANDIDATE_SUBMITTED | 候选人已提交 |
| MATCH_SUBMITTED | 匹配请求已提交 |
| MATCH_ACCEPTED | 匹配已接受 |
| MATCH_REJECTED | 匹配已拒绝 |
| MATCH_STATUS_FETCHED | 匹配状态已获取 |
| MATCH_LIST_FETCHED | 匹配列表已获取 |
| QUOTA_UPDATED | 配额已更新 |
| QUOTA_FETCHED | 配额已获取 |
| RULES_FETCHED | 规则已获取 |
| RATE_LIMIT_FETCHED | 限流配置已获取 |
| RATE_LIMIT_UPDATED | 限流配置已更新 |
| RATE_LIMITS_LISTED | 限流配置列表已获取 |

---

## 分页

列表类查询支持分页参数：

### 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| page | integer | 1 | 页码 |
| page_size | integer | 20 | 每页条数 |

### 响应格式

```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 100,
    "total_pages": 5
  }
}
```

---

## 幂等性

使用 `X-Idempotency-Key` header 避免重复操作：

```
X-Idempotency-Key: unique_key_here
```

- 相同 Key 的重复请求返回缓存的响应
- Key 有效期 1 小时
- 适用于 POST 类写操作

---

## 限流

### 请求 Headers

| Header | 说明 | 默认值 |
|--------|------|--------|
| X-Source | 请求来源标识 | 客户端IP |
| X-Action | 操作类型 | default |
| X-Tenant | 租户ID | default |

### 响应 Headers

| Header | 说明 |
|--------|------|
| X-RateLimit-Remaining | 剩余请求次数 |
| X-RateLimit-Limit | 限制次数 |
| X-RateLimit-Window | 时间窗口（秒） |

### 超限响应

```json
{
  "error": "Too Many Requests",
  "code": "ERR_QUOTA_EXCEEDED",
  "meta": {
    "limit": 100,
    "window": "1 hour",
    "retry_after": 3600,
    "source": "client_abc",
    "action": "submit_jd",
    "tenant": "default"
  }
}
```

---

## 指标暴露

#### GET /metrics

Prometheus 格式指标：

```
mediator_requests_total{action="submit_jd",status="approved"} 42
mediator_pending_count 3
mediator_approvals_total{decision="approved"} 30
mediator_quota_remaining{source="client_abc"} 850
```
