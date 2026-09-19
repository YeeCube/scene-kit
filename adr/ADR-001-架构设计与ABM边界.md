---
title: SceneKit架构设计与ABM边界
project: SceneKit
version_baseline: 0.6.0
status: proposed
updated: 2026-09-09
aliases:
  - SK架构设计
  - 世界模型运行时设计
tags:
  - scene-kit
  - world-model
  - ABM
---

# 架构设计与ABM边界

## 1. 定位

[[SceneKit]]（SK）是世界、空间、几何和交互式实体运行时 SDK。它不是 Scene Studio，也不是通用数学引擎。SK 的职责是把一组 Entity 组织成可持续运行、可观察、可暂停和可交互的世界。

当前 v0.6.0 已形成稳定基础：RECS EntityPool 桥接、`WorldModel`、`EntityKind`、几何对象、parent 嵌套、生命周期、行为注册、调度器、DataCollector、WorldSnapshot/WorldDelta、`ModelSession`、WebSocket 传输和 TypeScript 前端包。

## 2. ABM 在 SK 中的含义

ABM 在 SK 中不是一个另立的产品，而是 WorldModel 的一种使用方式和能力集合：

- Agent 以 `EntityKind(type="AGENT")` 存在；
- Agent 的状态以 RECS 的 SoA 列保存；
- Agent 通过 geometry、parent 和关系进入世界；
- Perception 提供自身属性、邻居、场和碰撞视图；
- BehaviorRegistry 或插件定义局部行为；
- Scheduler 决定 tick 内执行顺序；
- Lifecycle 管理出生、激活、停用和死亡；
- ModelSession 提供播放、暂停、单步、重置和受控修改；
- Snapshot/Delta 提供前端、记录器和下游消费者的状态边界。

因此，SK 的 ABM 是“实体世界运行时”，不是一套独立命名的框架。

## 3. 分层架构

```text
RECS
  ↓
EntityPoolBridge / SoA 数据层
  ↓
WorldModel Facade
  ├── EntityKind / parent / lifecycle
  ├── Geometry / embedding / perception
  ├── BehaviorRegistry / plugins
  ├── Scheduler / tick
  ├── Collector / metrics
  └── Snapshot / Delta / Session / Transport
        ↓
前端包、Scene Studio、CSL、其他下游消费者
```

SK 与 [[MathEngine]] 的关系是可选协作：SK 提供状态和邻域，ME 提供方程、求解、优化、统计和实验编排。SK 核心不得硬依赖 ME；需要时通过 adapter 或可插拔 step function 接入。

## 4. 与 ME 的边界

| 问题 | SK | ME |
|---|---|---|
| Agent 在哪里 | 负责 | 不负责运行时挂载 |
| 邻域与碰撞 | 负责查询和事件 | 可分析查询结果 |
| 行为如何触发 | 负责 tick/调度 | 提供行为方程 |
| 状态如何计算 | 调用方程并写回 | 负责方程、求解器和随机过程 |
| 多次实验 | 提供单次会话边界 | 负责实验编排、扫描和比较 |
| 统计与指标 | 采集原始数据 | 负责高级统计、拟合和分析 |
| 交互暂停/单步 | 负责 | 不负责 |

## 5. 兼容性策略

### 保持稳定

- `WorldModel`、`EntityKind`、`ModelSession` 的公开入口；
- `WorldSnapshot`/`WorldDelta` envelope 和列式批次结构；
- 命令类型与 `CommandResult`；
- `(kind, uid)` 稳定实体标识；
- TypeScript 包的协议类型和校验入口。

### 允许演进

- 内部几何实现、空间索引和邻域算法；
- 行为注册表的新增行为；
- ME adapter、求解器和后端选择策略；
- v0.x 之后的协议扩展字段，但必须保持旧字段语义。

### 发布要求

任何改变公开 API、快照字段或调度语义的版本，都必须更新 `CHANGELOG.md`、`docs/下游消费者集成指南.md` 和迁移说明。架构优先于短期兼容时，使用新版本发布，不在旧版本中静默改变行为。

## 6. ABM 扩展路线

1. 固化现有 `EntityKind + Perception + Behavior + Scheduler` 组合；
2. 增加显式的邻域视图和动作结果协议；
3. 增加连续时间求解钩子，但保持 tick 会话语义；
4. 增加空间索引、场和跨 geometry 交互；
5. 增加可选 ME adapter；
6. 增加回放、检查点和实验批量运行。

## 7. 非目标

- 不把 ME 的符号 AST、外部后端调度器复制到 SK；
- 不把 LLM、RL、MARL 等 AI 产品能力放入 SK 核心；
- 不为 ABM 建立独立顶层产品或独立仓库；
- 不读取或依赖机密下游应用的内部实现。
