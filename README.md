# zhongjie — AI 协作平台

[![Tests](https://github.com/qing3a/zhongjie-platform/actions/workflows/test.yml/badge.svg)](https://github.com/qing3a/zhongjie-platform/actions/workflows/test.yml)
[![Version](https://img.shields.io/badge/version-0.3.0--alpha-orange)](https://github.com/qing3a/zhongjie-platform/releases)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)

> **🚧 v0.3 重定位进行中 (2026-06-15)**
>
> 旧定位"猎头中介 / agent 协作网络"是 v0.2 阶段的工程假设，**不是终局产品目标**。
> v0.3 起重定位为 **"AI 深度参与的本地生活服务 + 招聘协作平台，以 API 为核心"**——
> 详见 [`docs/v0.3-architecture.md`](docs/v0.3-architecture.md)。
> v0.2 全部 API 端点**保留向后兼容**，可继续使用。

**AI 深度参与的本地生活服务 + 招聘协作平台，以 API 为核心。**

5 类用户：求职者 / BOSS·HR / 服务提供者 / 服务需求方 / 管理员。
10 个核心 API 模块：身份、信息发布、智能匹配、AI 即时通讯、审核风控、交易流程、评价信誉、数据洞察、协作任务、开放集成。

**所有能力封装为 API**——你可以构建任何形态的应用（移动端 / Web / 小程序 / 内部系统），甚至直接将它作为中台嵌入其他业务。

## 快速开始

## 快速开始

```bash
# 1. 检查环境配置
python check_env.py

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python start.py
# 或指定端口: PORT=9000 python start.py
```

访问 http://localhost:8000/docs 查看 Swagger 文档

## 环境变量

在 `.env` 文件或环境变量中配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| DATA_DIR | data | 数据存储目录 |
| LOG_LEVEL | INFO | 日志级别 |
| PORT | 8000 | 服务端口 |
| RATE_LIMIT_MAX | 100 | 限流：最大请求数 |
| RATE_LIMIT_WINDOW | 60 | 限流：时间窗口（秒） |
| SQLITE_ENABLED | false | 是否启用 SQLite |
| SQLITE_DB_PATH | data/mediator.db | SQLite 数据库路径 |

## API 端点完整列表

### 认证

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/auth/token | 生成 API Token |
| POST | /api/auth/revoke/{key_id} | 撤销 API Key |
| GET | /api/auth/keys | 列出所有 API Keys |

### 请求 (P0)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/request | 提交请求 |
| GET | /api/request/{request_id} | 查询请求详情 |

### 审批台 (P1)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/pending | 待审批列表 |
| POST | /api/approval/{request_id}/approve | 审批通过 |
| POST | /api/approval/{request_id}/reject | 审批拒绝 |
| GET | /api/approvals | 审批历史 |

### 路由 (P2)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/route/{request_id} | 路由分发 |
| GET | /api/routes | 路由列表 |
| POST | /api/route/{route_id}/reply | 接收回复 |

### 规则管理 (P3)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/rules | 规则列表 |
| POST | /api/rules | 添加规则 |
| PUT | /api/rules/{rule_id} | 更新规则 |
| DELETE | /api/rules/{rule_id} | 删除规则 |

### 配额系统 (P3)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/quota/{source} | 查询配额 |
| PUT | /api/quota/{source} | 设置配额 |
| GET | /api/waiting | 查看等待队列 |

### Webhook (P3)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/webhooks | 注册 Webhook |
| GET | /api/webhooks | 列出 Webhooks |
| DELETE | /api/webhooks/{webhook_id} | 取消注册 |

### 回调系统 (P3)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /api/callbacks/register | 注册回调 |
| GET | /api/callbacks | 列出回调 |
| DELETE | /api/callbacks/{callback_id} | 删除回调 |

### 计费与审计 (P3)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /api/billing | 计费汇总 |
| GET | /api/audit | 审计日志 |
| GET | /api/security | 安全事件 |

### Skill Link (统一入口)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | /skill/{skill_name}/{action} | Skill POST 入口 |
| GET | /skill/{skill_name}/{action} | Skill GET 入口 |
| POST | /api/batch | 批量请求 |

### 健康与监控

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /health/live | 进程存活检查 |
| GET | /health/ready | 依赖就绪检查 |
| GET | /metrics | Prometheus 指标 |
| GET | / | 根路径 |

## Skill Link 协议

Skill Link 是平台的统一接口规范，让 Agent 更容易理解和调用平台能力。

### 响应格式

所有 Skill Link 端点返回统一响应格式：

```json
{
  "status": "success|error|pending",
  "code": "错误码或业务码",
  "data": {...},
  "message": "说明文字",
  "meta": {
    "request_id": "req_xxx",
    "timestamp": "2026-05-31T10:30:00Z",
    "version": "1.0"
  }
}
```

### 状态说明

- `success`: 操作成功
- `error`: 操作失败
- `pending`: 操作待处理（异步场景）

### 可用 Skills

**猎头_skill**

| 动作 | 功能 |
|------|------|
| submit_jd | 提交职位 JD |
| submit_candidate | 提交候选人 |
| submit_match | 提交匹配请求 |
| get_match_status | 查询匹配状态 |

**甲方_skill**

| 动作 | 功能 |
|------|------|
| get_pending_matches | 获取待处理匹配列表 |
| reply_interview | 回复面试邀请 |
| close_jd | 关闭 JD |

**平台_skill**

| 动作 | 功能 |
|------|------|
| approve | 审批通过 |
| reject | 审批拒绝 |
| get_rules | 获取规则列表 |
| get_quota | 查询配额 |
| update_quota | 更新配额 |
| get_pending_requests | 获取待审批请求 |
| get_retries | 获取重试状态 |
| retry | 手动触发重试 |
| export_data | 数据导出 |
| get_rate_limit | 获取限流配置 |
| update_rate_limit | 更新限流配置 |
| list_rate_limits | 列出所有限流配置 |

### 分页支持

列表类查询支持分页参数：

- `page`: 页码（默认 1）
- `page_size`: 每页条数（默认 20）

## 核心功能

### P0: 规则引擎

- 统一请求格式（source, target, intent, payload）
- 规则按优先级遍历，命中即终止
- 支持条件：==, !=, >, <, in, not_in, contains
- Action 类型：auto_approve, auto_reject, manual_review

### P1: 审批台

- 待审批队列 + 审批建议
- 人工审批通过/拒绝 + 审批记录
- 审批历史查询

### P2: 路由分发

- 已审批请求路由到目标 Skill
- 接收目标方回复
- 路由状态跟踪

### P3: 规则管理与 Webhook

- 规则 CRUD，热更新
- 配额系统（每小时滑动窗口）
- Webhook 回调（5 种事件）

## 测试

```bash
python -m pytest -v
```

280+ 测试用例，覆盖规则引擎、审批台、路由、配额、Webhook、A2A 协议、委托治理、信任分、事件 wiring。

## 项目结构

```
zhongjie/
├── start.py             # 启动脚本
├── check_env.py         # 环境检查
├── pyproject.toml       # 包定义 (src 布局)
├── requirements.txt     # 依赖清单
├── src/zhongjie/        # 主代码 (六层架构)
│   ├── api/             # FastAPI 路由层
│   ├── protocol/        # Skill Link / A2A 协议
│   ├── collaboration/   # 委托/任务/交接
│   ├── governance/      # 规则引擎/审批/审计/信任
│   ├── domain/          # 候选人/JD/Match 实体
│   ├── identity/        # Agent 身份/认证/信任
│   ├── infra/           # 持久化/事件/计费
│   └── utils.py         # 横切工具
├── tests/               # 单元测试 (29 个文件, 280+ 用例)
├── examples/            # e2e 演示
├── scripts/             # 运维/迁移脚本
├── web/                 # 管理后台
└── docs/                # 架构设计文档
```

## 适用场景

- 猎头中介：职位 JD ↔ 候选人简历 匹配
- API 网关：外部请求的审批过滤
- 数据交换：敏感信息脱敏后路由
- 任何需要"控制权 + 可追溯性"的场景