# Changelog

## [0.2.0] - 2026-06-15

首个正式发布版本。从 P0-P5 重构完成, 老代码 (api_server.py / p0_core.py / p1_p2.py / 根目录 auth.py) 全部清除。

### 新增

- **六层架构** (api / protocol / collaboration / governance / domain / identity / infra) + 横切 utils
- **A2A Protocol 适配**: tasks/send, tasks/get, tasks/cancel, message/send, /.well-known/agent-card.json
- **委托协作**: 防飞单 (Provenance + Visibility), 分润上链 (FeeShare), 并发互斥
- **A2A 信任驱动治理**: trust_score 事件驱动调整, 0.85 高信任自动通过 / 0.30 低信任强制审批
- **AppendOnlyAuditLog**: 链式 hash 防篡改, verify_integrity
- **Skill Link 协议**: 统一响应格式 {status, code, data, message, meta}, build_skill_response + translate_state_error
- **e2e demo** (examples/e2e_demo.py): 12 步演示完整委托流, 验证 trust / ACL / 审计 / billing

### 修复 (相对 refactor 期)

- TrustStrategy 必须在 app lifespan 启动时 wire, 否则业务事件触发不到
- Delegation fee_split 硬校验, 避免静默吞错导致财务事故
- 同一候选人同时只允许一条 active 委托 (防飞单)
- A2A dispatcher 推进/新建双路径错误处理一致性
- Token.agent_id 实时从 Key 同步, 防止 key 重绑后越权
- DATA_DIR env var 全单例生效 (get_data_dir 集中)

### 移除

- 老 `api_server.py` (3380 行), `p0_core.py`, `p1_p2.py`, 根目录 `auth.py`
- 老 `demo_workflow.py`, `test_p1_p2.py`, `test_callback.py`, `test_token_with_agent.py`
- `start.py --legacy` 兜底分支
- `migrate_to_sqlite.py` 移到 `scripts/` 下

### 已知问题

- `scripts/migrate_add_owner.py` 输出含 emoji, Windows GBK 控制台需 `PYTHONIOENCODING=utf-8`
  (pytest 的 `test_migration.py` 5 个测试因此失败, 与本次发布无关)
