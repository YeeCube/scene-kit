# Changelog

本文件记录 `scene-kit`（Python 引擎 `scene_kit` + TypeScript SDK `@scene-kit/*`）的重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

---

## 发版策略声明（2026-09-07 联合项目组拍板）

**SK 独立 semver，与 SA app 版本解耦。**

| 维度 | 决策 |
|------|------|
| 版本号 | `scene-kit` 自身 semver（当前 `0.6.0`），独立演进 |
| 消费者约束 | 下游以 `scene-kit>=0.6.0` 声明依赖（CSL/ES 现用 `>=0.2.0`） |
| Changelog | 由 SK 仓库（本文件）维护 |
| 发版节奏 | 跟随 SK 功能迭代，**不绑定 SA（scene-studio）或 MUI 的发版** |
| 本地开发 | 开发期继续用 `uv.sources` 可编辑路径（`file:`/本地源映射），发布时切正式版本 |

**理由**：CSL（ComplexSystemLab）、ES（EntelechySystem）把 SK 当独立包消费（声明 `>=0.2.0`），若与 SA app 版本耦合会显著增加跨项目协调成本。SK 定位为**通用世界建模层（L3）**，是领域无关的 interchange 抽象，服务全体下游（YG/YGE · CSL · ES · Matheshop），而非某个特定 app。

**跨项目独立性约束**：SK 的 API（WorldModel/EntityKind/WorldSnapshot/WorldDelta/WorldPlugin）必须保持领域无关，不得引入游戏专属术语（如 MovePrim、棋类坐标）。任何消费者都应能在不修改自身代码的前提下直接消费 SK。

---

## [Unreleased]（v0.7.0 开发中）

### Added

- **关系登记与投影（M1）**：`WorldModel.bind / unbind / relations()` 命名边表 API（RECS `Relation`，(srcUid,dstUid) 去重）；`WorldSnapshot.relationBatches` 首次落地列式投影（`{name, srcKind, dstKind, count, schema, columns}`，`SnapshotProjection.include_relations` 生效）；`diff_snapshots` 输出关系 added/removed/changed 增量；快照校验新增 relation batch 结构校验（uid 字符串编码 + 边唯一性）。
- `@scene-kit/vue` 命令面扩展：select/clearSelection/getSelection/batchMove/batchSetAttribute/bindRelation/unbindRelation/snapToSlots；新增 `demos/demo_checkers.py`（跳棋草稿盘，逻辑吸附验收场景）。
- 架构决策：`adr/ADR-002-世界线批处理与吸附语义.md`（accepted，内部决策记录，不在公开 docs 区）——世界线 DAG、SelectionSet 批处理、逻辑吸附、Always-On、AI 边界契约。
- **SelectionSet 与批处理命令（M2，ADR-002 D2）**：`ModelSession` 新增 `select`（按 uids 或 rect 框选，replace/add/remove 模式）、`clear_selection`、`get_selection`、`batch_move`、`batch_set_attribute`（对选择集扇出，封闭宏集合）。选择集是会话态，不进快照。
- **TS 关系增量应用（M2）**：`applyWorldDelta` 支持 relationBatches 增量（added/removedEdges/changed），delta 通道下关系实时到达前端。
- **关系命令与逻辑吸附（M2，ADR-002 D3）**：新增 `bind_relation` / `unbind_relation` / `snap_to_slots`（半径内最近落点，对齐坐标并生成 `is_on` 关系边；未传 uids 时作用于选择集）。`despawn` 级联 unbind 出入边并修剪选择集（清偿 M1 悬空边限制）。

### Changed

- **协议命名空间**：`wmk.world-snapshot` / `wmk.world-delta` → `scene-kit.world-snapshot` / `scene-kit.world-delta`，`protocolVersion` 1.0 → 1.1（Python 与 `@scene-kit/core`、SA fixture 同步）。已知限制：实体 kill 不自动级联 unbind（悬空边原样导出），M2 已在命令层清偿（despawn 级联 unbind）。

---

## [0.6.0]

### Added

- **交互协议**：`WorldSnapshot` / `WorldDelta` 正式前后端协议；按 `EntityKind` 分批、按字段列式导出（SoA），实体以 `(kind, uid)` 稳定标识。
- **传输层**：msgpack 序列化、WebSocket 重连、心跳与可选鉴权钩子。
- **运行时会话**：`ModelSession` 支持运行（play）、暂停（pause）、单步（step）、重置（reset）及实体增删改移动。
- **前端 SDK**：`@scene-kit/core`、`@scene-kit/vue`、`@scene-kit/renderer-2d`、`@scene-kit/main-ui-adapter` 四包，可独立以 `file:` 依赖被 Studio 消费。
- 真实接入示例见 `docs/API_手册.md` 与 `docs/下游消费者集成指南.md`。

### Notes（联合项目组架构现状，2026-09-07）

- **L3 通用世界建模层定位确认**：SK 为领域无关的世界建模 SDK，消费者谱系为 YG/YGE · CSL · ES · Matheshop（详见 `YG_design/YG-notes/notes/备忘录-YG+SS+MUI联合项目组引擎选型会-20260905-001.md` §2.2 会后修正）。
- **WorldSnapshot 定位升级**：从「SA↔YG 双边协议」升级为「SK 全消费者通用 interchange format」。
- **前端渲染底座迁移**：SA（scene-studio）已在 Phase 2a 将渲染底座从 `@scene-kit/renderer-2d` + `main-ui-adapter` 迁移到 `@main-ui/view-world`（L1 视口层，MUI 仓库）。SK 前端 SDK 的 `renderer-2d`/`main-ui-adapter` 仍保留以兼容其它消费者，但不再是 SA 的渲染路径。架构分层：L0 PixiJS · L1 @main-ui/view-world · L2 YGE · L3 SK scene_kit · L4 RECS · L∞ MUI。

---

## [0.5.1]

### Changed

- **品牌终局**：伞形品牌调整为 **Scene Suite**（场景套件），应用仓库 `scene-sandbox` → **`scene-studio`**（场景工作室，闭源）。对齐 autodo 系列命名：suite 伞形 + kit SDK + studio/app 应用。
- **仓库拆分**：SDK（本仓库，开源）与应用（`scene-studio`，闭源）为两个同级仓库。伞形品牌 **Scene Suite** 不再对应独立仓库，仅作为品牌屋/聚合工作区存在于各仓库文档。

---

## [0.5.0]

### Changed

- **仓库拆分**：SDK（本仓库，开源）与应用（原 `scene-sandbox`，闭源）拆分为两个同级仓库。
- 仓库与包名统一为 `scene-kit`：Python 导入路径为 `scene_kit`，npm 包名为 `@scene-kit/*`。

### Added

- `WorldSnapshot` / `WorldDelta` 作为正式前后端协议。
- `ModelSession` 与可选 WebSocket 服务，提供播放、暂停、单步、重置与受控状态修改。
- `frontend/` PNPM workspace，提供 `@scene-kit/core`、`@scene-kit/vue`、`@scene-kit/renderer-2d`、可选 `main-ui` 适配器。

### Notes

- **命名演变**：`world-model-kit`（2026-07-15 起）→ `sceneforge`（2026-08-10）→ `scene-studio`（2026-08-11，伞形）→ `scene-kit`（SDK，2026-08-12）→ `scene-suite` 伞形 + `scene-studio` 应用（2026-08-12，终局）。
