"""
L1 Infrastructure
- persistence.py: 存储 (JSON / SQLite 切换)
- webhooks.py: Webhook 管理 (复用 p1_p2.py:1494)
- callbacks.py: 异步回调
- billing.py: 计费 (M2 拆分到 agent 维度)
- quota.py: 配额
- retry.py: 重试
- config.py: 配置
- events.py: 事件总线 (后续)
"""
