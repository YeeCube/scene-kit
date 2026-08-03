# world-model-kit

世界模型工具包 —— 基于 RECS（relation-entity-component-system-kit，SoA ECS 引擎）的高性能 Agent-Based Modeling 工具包。

## 结构

- `world_model_kit/`：实际包定义（distribution 名 `world-model-kit`，提供 `world_model_kit` 模块）
- `tests/`：单元测试
- `demos/`：示例程序
- `docs/`：API 手册、用户手册、开发者指南、开发日志

## 安装

```bash
uv sync                      # 默认安装核心依赖
uv sync --extra dev          # 安装开发依赖（pytest、ruff、mypy）
uv sync --all-extras         # 安装全部可选组（dev + visualization + torch + mlx + jax）
```

## 本地依赖

- `relation-entity-component-system-kit`：由 `[tool.uv.sources]` 映射到 `../relation-entity-component-system`（本地仓库）
