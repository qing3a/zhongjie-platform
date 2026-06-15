# Contributing to zhongjie

欢迎贡献！本项目是**中介 API 平台** (zhongjie) —— 一个 Agent 协作网络底座。

## 开发环境

- Python 3.10+
- Git
- 推荐: Windows / macOS / Linux 都能跑（CI 在 `ubuntu-latest` + `windows-latest` 各跑一次）

## 快速上手

```bash
# 1. 克隆
git clone https://github.com/qing3a/zhongjie-platform.git
cd zhongjie-platform

# 2. 安装依赖（editable 模式）
pip install -e ".[dev]"

# 3. 跑测试
python -m pytest -v

# 4. 启动服务
python start.py
# 访问 http://localhost:8000/docs

# 5. 跑端到端 demo (12 步)
PYTHONIOENCODING=utf-8 DATA_DIR=demo_run/data python examples/e2e_demo.py
```

## 项目结构

```
zhongjie-platform/
├── start.py                  # 启动脚本
├── pyproject.toml            # 包定义 (src 布局)
├── CHANGELOG.md              # 发布记录
├── src/zhongjie/             # 主代码 (六层架构)
│   ├── api/                  # FastAPI 路由
│   ├── protocol/             # Skill Link / A2A 协议
│   ├── collaboration/        # 委托/任务/交接
│   ├── governance/           # 规则引擎/审批/审计/信任
│   ├── domain/               # 候选人/JD/Match 实体
│   ├── identity/             # Agent 身份/认证/信任
│   ├── infra/                # 持久化/事件/计费
│   └── utils.py              # 横切工具
├── tests/                    # 280+ 单元测试
├── examples/                 # e2e 演示
├── scripts/                  # 运维/迁移脚本
├── web/                      # 管理后台
├── docs/                     # 架构设计文档
└── .github/workflows/        # GitHub Actions CI
```

## 提交规范

- **Commit message**: 动词开头，描述**为什么**而非**做了什么**
- **PR 标题**: 简短描述变更
- **必须**: PR 通过 `pytest -v` 全部通过 + 无新增 lint 错误
- **建议**: 一个 PR 一个主题（修一个 bug、加一个 feature、refactor 一个小区域）

## 测试约定

```bash
# 跑所有
python -m pytest -v

# 跑一个文件
python -m pytest tests/test_X.py -v

# 跑一个用例
python -m pytest tests/test_X.py::test_y -v
```

测试夹具（`tmp_path`、`monkeypatch`）已覆盖 `DATA_DIR` 隔离，不需要手动清理。

## 编码风格

- 类型注解: 强制（`mypy --strict` 兼容）
- Docstring: 公开函数/类必须，中文/英文均可
- 错误处理: 不静默吞 `Exception`；状态机错误 → 业务码（HTTP 4xx）；其他 → 内部错（HTTP 5xx）
- 跨切工具: 放 `src/zhongjie/utils.py`（不要建 `utils/` 包，除非有第三类工具）

## 报告问题

GitHub Issues: https://github.com/qing3a/zhongjie-platform/issues

## 行为准则

尊重、专业、建设性。本项目维护者承诺对所有贡献者一视同仁。
