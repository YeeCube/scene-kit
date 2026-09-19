"""模型会话、命令队列与 tick 边界控制。"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import replace
from threading import RLock
from typing import Any
from uuid import uuid4

import numpy as np

from scene_kit.protocol import (
    CommandResult,
    SnapshotProjection,
    WorldCommand,
    diff_snapshots,
)
from scene_kit.world import WorldModel

ModelFactory = Callable[[Mapping[str, Any]], WorldModel]


class ModelSession:
    """拥有一个 WorldModel 的交互式运行会话。

    命令由 ``dispatch`` 或 ``enqueue_command`` 进入队列，并在模型 step 之间
    执行。相机、面板和临时选中等前端状态不进入此队列。
    """

    def __init__(
        self,
        model: WorldModel,
        *,
        model_factory: ModelFactory | None = None,
        parameters: Mapping[str, Any] | None = None,
        projection: SnapshotProjection | Mapping[str, Any] | None = None,
        name: str = "world-model",
    ) -> None:
        self.model = model
        self.model_factory = model_factory
        self.parameters: dict[str, Any] = dict(parameters or {})
        self.projection = SnapshotProjection.from_value(projection)
        self.name = name
        self.playing = False
        self.rate = 10.0
        self._commands: deque[WorldCommand] = deque()
        self._lock = RLock()
        self._previous_snapshot: dict[str, Any] | None = None
        # SelectionSet：会话态选择集（kind -> uid 列表），不进快照（ADR-002 D2）
        self._selection: dict[str, list[str]] = {}

    @property
    def capabilities(self) -> dict[str, Any]:
        return {
            "commands": [
                "get_snapshot",
                "play",
                "pause",
                "step",
                "reset",
                "set_rate",
                "set_parameter",
                "spawn",
                "despawn",
                "move",
                "set_attribute",
                "set_tag",
                "select",
                "clear_selection",
                "get_selection",
                "batch_move",
                "batch_set_attribute",
                "bind_relation",
                "unbind_relation",
                "snap_to_slots",
            ],
            "snapshot": True,
            "delta": True,
            "seek": False,
            "reset": self.model_factory is not None,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tick": self.model.tick,
            "playing": self.playing,
            "rate": self.rate,
            "parameters": dict(self.parameters),
            "capabilities": self.capabilities,
        }

    @staticmethod
    def _normalize_command(command: WorldCommand | Mapping[str, Any]) -> WorldCommand:
        if isinstance(command, WorldCommand):
            return command
        command_type = command.get("type")
        if not isinstance(command_type, str) or not command_type:
            raise ValueError("command.type 必须是非空字符串")
        command_id = command.get("commandId", command.get("command_id"))
        if command_id is None:
            command_id = str(uuid4())
        payload = command.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError("command.payload 必须是对象")
        return WorldCommand(type=command_type, command_id=str(command_id), payload=payload)

    def enqueue_command(self, command: WorldCommand | Mapping[str, Any]) -> str:
        normalized = self._normalize_command(command)
        with self._lock:
            self._commands.append(normalized)
        return normalized.command_id

    def dispatch(self, command: WorldCommand | Mapping[str, Any]) -> CommandResult:
        """在当前 tick 与下一次 step 之间立即处理一个命令。"""
        normalized = self._normalize_command(command)
        with self._lock:
            return self._apply_command(normalized)

    def process_commands(self) -> list[CommandResult]:
        results: list[CommandResult] = []
        with self._lock:
            while self._commands:
                results.append(self._apply_command(self._commands.popleft()))
        return results

    def _indices_for_uids(self, kind: str, uids: Any) -> np.ndarray:
        if kind not in self.model.list_kinds():
            raise KeyError(f"未知 EntityKind: {kind}")
        uid_strings = [str(value) for value in np.atleast_1d(uids).tolist()]
        pool = self.model.get_pool(kind)
        raw = pool.d["i"][: pool.size]
        uid_values = raw if isinstance(raw, np.ndarray) else pool.backend.to_numpy(raw)
        lookup = {str(int(uid)): index for index, uid in enumerate(np.asarray(uid_values))}
        missing = [uid for uid in uid_strings if uid not in lookup]
        if missing:
            raise KeyError(f"{kind} 中不存在 UID: {missing}")
        return np.asarray([lookup[uid] for uid in uid_strings], dtype=np.int64)

    def _spawn(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(payload["kind"])
        attrs = payload.get("attrs", {})
        if not isinstance(attrs, Mapping):
            raise ValueError("spawn.attrs 必须是对象")
        indices = self.model.spawn(kind, n=int(payload.get("n", 1)), **dict(attrs))
        pool = self.model.get_pool(kind)
        raw = pool.d["i"][indices]
        uids = raw if isinstance(raw, np.ndarray) else pool.backend.to_numpy(raw)
        return {"entities": [{"kind": kind, "uid": str(int(uid))} for uid in np.asarray(uids)]}

    def _set_attribute(self, payload: Mapping[str, Any]) -> None:
        kind = str(payload["kind"])
        field = str(payload["field"])
        if field in {"i", "o", "_kind", "_active", "_step_fn", "_parent_id", "_type"} or field.startswith("_"):
            raise ValueError(f"'{field}' 不是可编辑属性")
        pool = self.model.get_pool(kind)
        if field not in pool.d:
            raise ValueError(f"'{field}' 不存在于 {kind}")
        indices = self._indices_for_uids(kind, payload.get("uids", []))
        self.model.set_attr(kind, field, indices, payload.get("values"))

    # ------------------------------------------------------------------
    # SelectionSet 与批处理（ADR-002 D2）
    # ------------------------------------------------------------------

    def _uids_of_kind(self, kind: str, indices: np.ndarray | None = None) -> list[str]:
        pool = self.model.get_pool(kind)
        raw = pool.d["i"][: pool.size] if indices is None else pool.d["i"][indices]
        values = raw if isinstance(raw, np.ndarray) else pool.backend.to_numpy(raw)
        return [str(int(uid)) for uid in np.asarray(values)]

    def _select(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        kind = str(payload["kind"])
        if kind not in self.model.list_kinds():
            raise KeyError(f"未知 EntityKind: {kind}")
        mode = str(payload.get("mode", "replace"))
        rect = payload.get("rect")
        if "uids" in payload:
            uids = [str(value) for value in np.atleast_1d(payload["uids"]).tolist()]
        elif rect is not None:
            pool = self.model.get_pool(kind)
            active = self.model._lifecycle[kind].active_indices
            if len(active) == 0 or "u" not in pool.d or "v" not in pool.d:
                uids = []
            else:
                u = np.asarray(pool.d["u"][: pool.size], dtype=np.float64)[active]
                v = np.asarray(pool.d["v"][: pool.size], dtype=np.float64)[active]
                mask = (
                    (u >= float(rect.get("u_min", -np.inf)))
                    & (u <= float(rect.get("u_max", np.inf)))
                    & (v >= float(rect.get("v_min", -np.inf)))
                    & (v <= float(rect.get("v_max", np.inf)))
                )
                uids = self._uids_of_kind(kind, active[np.asarray(mask, dtype=bool)])
        else:
            raise ValueError("select 需要 uids 或 rect 之一")
        current = self._selection.get(kind, [])
        if mode == "add":
            merged = list(dict.fromkeys([*current, *uids]))
        elif mode == "remove":
            drop = set(uids)
            merged = [uid for uid in current if uid not in drop]
        else:
            merged = list(dict.fromkeys(uids))
        if merged:
            self._selection[kind] = merged
        else:
            self._selection.pop(kind, None)
        return {"selection": {k: list(v) for k, v in self._selection.items()}}

    def _selected_pairs(self, kinds: Any) -> list[tuple[str, list[str]]]:
        wanted = {str(k) for k in kinds} if kinds else set(self._selection)
        return [(kind, list(uids)) for kind, uids in self._selection.items() if kind in wanted]

    def _batch_move(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        delta = np.asarray(payload["delta"], dtype=np.float32)
        applied: dict[str, int] = {}
        for kind, uids in self._selected_pairs(payload.get("kinds")):
            pool = self.model.get_pool(kind)
            if "u" not in pool.d or "v" not in pool.d:
                continue
            indices = self._indices_for_uids(kind, uids)
            self.model.move(kind, indices, delta)
            applied[kind] = len(uids)
        return {"applied": applied}

    def _batch_set_attribute(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        field = str(payload["field"])
        if field in {"i", "o", "_kind", "_active", "_step_fn", "_parent_id", "_type"} or field.startswith("_"):
            raise ValueError(f"'{field}' 不是可编辑属性")
        applied: dict[str, int] = {}
        for kind, uids in self._selected_pairs(payload.get("kinds")):
            pool = self.model.get_pool(kind)
            if field not in pool.d:
                continue
            indices = self._indices_for_uids(kind, uids)
            self.model.set_attr(kind, field, indices, payload.get("value"))
            applied[kind] = len(uids)
        return {"applied": applied}

    # ------------------------------------------------------------------
    # 关系命令与逻辑吸附（ADR-002 D3）
    # ------------------------------------------------------------------

    def _bind_relation(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        name = str(payload["name"])
        attrs = payload.get("attrs", {})
        if not isinstance(attrs, Mapping):
            raise ValueError("bind_relation.attrs 必须是对象")
        count = self.model.bind(
            name,
            str(payload["srcKind"]),
            str(payload["dstKind"]),
            payload.get("srcUids", []),
            payload.get("dstUids", []),
            **dict(attrs),
        )
        return {"name": name, "count": count}

    def _unbind_relation(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        name = str(payload["name"])
        count = self.model.unbind(
            name,
            src_uids=payload.get("srcUids"),
            dst_uids=payload.get("dstUids"),
        )
        return {"name": name, "count": count}

    def _snap_to_slots(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """把选中（或指定）实体吸附到最近的落点实体并生成逻辑绑定。

        落点 = ``slot_kind`` 的 point geometry 活跃实体；半径内取最近者，
        ``align=True``（默认）时把实体坐标对齐到落点，并 bind ``relation``
        （默认 ``is_on``）边（ADR-002 D3：吸附提交生成 Relation）。
        """
        kind = str(payload["kind"])
        slot_kind = str(payload["slotKind"])
        radius = float(payload.get("radius", 1.0))
        relation = str(payload.get("relation", "is_on"))
        align = bool(payload.get("align", True))
        uids = payload.get("uids")
        if uids is None:
            uids = self._selection.get(kind, [])
        uids = [str(value) for value in np.atleast_1d(uids).tolist()]
        if not uids:
            return {"snapped": [], "skipped": []}
        pool = self.model.get_pool(kind)
        slot_pool = self.model.get_pool(slot_kind)
        slot_active = self.model._lifecycle[slot_kind].active_indices
        if len(slot_active) == 0:
            return {"snapped": [], "skipped": list(uids)}
        slot_u = np.asarray(slot_pool.d["u"][: slot_pool.size], dtype=np.float64)[slot_active]
        slot_v = np.asarray(slot_pool.d["v"][: slot_pool.size], dtype=np.float64)[slot_active]
        slot_uids = np.asarray(self._uids_of_kind(slot_kind, slot_active))
        indices = self._indices_for_uids(kind, uids)
        ent_u = np.asarray(pool.d["u"][: pool.size], dtype=np.float64)[indices]
        ent_v = np.asarray(pool.d["v"][: pool.size], dtype=np.float64)[indices]
        snapped: list[dict[str, Any]] = []
        skipped: list[str] = []
        hit_local: list[int] = []
        hit_slot: list[int] = []
        for local, (eu, ev) in enumerate(zip(ent_u.tolist(), ent_v.tolist())):
            distances = np.hypot(slot_u - eu, slot_v - ev)
            nearest = int(np.argmin(distances))
            if distances[nearest] <= radius:
                snapped.append({"uid": uids[local], "slotUid": str(slot_uids[nearest])})
                hit_local.append(local)
                hit_slot.append(nearest)
            else:
                skipped.append(uids[local])
        if snapped:
            if align:
                self.model.move_to(
                    kind,
                    indices[np.asarray(hit_local, dtype=np.int64)],
                    slot_u[np.asarray(hit_slot, dtype=np.int64)],
                    slot_v[np.asarray(hit_slot, dtype=np.int64)],
                )
            self.model.bind(
                relation,
                kind,
                slot_kind,
                np.asarray([int(item["uid"]) for item in snapped], dtype=np.int64),
                np.asarray([int(item["slotUid"]) for item in snapped], dtype=np.int64),
            )
        return {"snapped": snapped, "skipped": skipped}

    def _cascade_unbind(self, kind: str, uids: list[str]) -> None:
        """实体消亡时级联清理其出入边（清偿 M1 悬空边限制）。"""
        for name, meta in list(self.model.relations().items()):
            if meta["srcKind"] == kind:
                self.model.unbind(name, src_uids=uids)
            if meta["dstKind"] == kind:
                self.model.unbind(name, dst_uids=uids)

    def _apply_command(self, command: WorldCommand) -> CommandResult:
        try:
            data: dict[str, Any] = {}
            payload = command.payload
            if command.type == "get_snapshot":
                data = {"snapshot": self.snapshot()}
            elif command.type == "play":
                self.playing = True
            elif command.type == "pause":
                self.playing = False
            elif command.type == "step":
                steps = max(1, int(payload.get("steps", 1)))
                for _ in range(steps):
                    self.model.step()
            elif command.type == "reset":
                if self.model_factory is None:
                    raise RuntimeError("当前会话没有 model_factory，不能 reset")
                self.model = self.model_factory(dict(self.parameters))
                self.playing = False
                self._previous_snapshot = None
                self._selection = {}
            elif command.type == "set_rate":
                rate = float(payload["rate"])
                if not np.isfinite(rate) or rate <= 0:
                    raise ValueError("rate 必须是正数")
                self.rate = rate
            elif command.type == "set_parameter":
                name = str(payload["name"])
                value = payload.get("value")
                self.parameters[name] = value
                resource = self.model.get_resource(dict)
                if isinstance(resource, dict):
                    resource[name] = value
                data = {"name": name, "value": value, "requiresReset": True}
            elif command.type == "spawn":
                data = self._spawn(payload)
            elif command.type == "despawn":
                kind = str(payload["kind"])
                uids = [str(value) for value in np.atleast_1d(payload.get("uids", [])).tolist()]
                indices = self._indices_for_uids(kind, uids)
                self.model.kill(kind, indices)
                self._cascade_unbind(kind, uids)
                self._selection[kind] = [
                    uid for uid in self._selection.get(kind, []) if uid not in set(uids)
                ]
                if not self._selection.get(kind):
                    self._selection.pop(kind, None)
            elif command.type == "move":
                kind = str(payload["kind"])
                indices = self._indices_for_uids(kind, payload.get("uids", []))
                self.model.move(kind, indices, np.asarray(payload["delta"], dtype=np.float32))
            elif command.type == "set_attribute":
                self._set_attribute(payload)
            elif command.type == "set_tag":
                kind = str(payload["kind"])
                field = str(payload["field"])
                if field not in self.model._kind_defs[kind].tags:
                    raise ValueError(f"'{field}' 不是 {kind} 的公开 tag")
                indices = self._indices_for_uids(kind, payload.get("uids", []))
                self.model.set_attr(kind, field, indices, payload.get("values"))
            elif command.type == "select":
                data = self._select(payload)
            elif command.type == "clear_selection":
                self._selection = {}
                data = {"selection": {}}
            elif command.type == "get_selection":
                data = {"selection": {k: list(v) for k, v in self._selection.items()}}
            elif command.type == "batch_move":
                data = self._batch_move(payload)
            elif command.type == "batch_set_attribute":
                data = self._batch_set_attribute(payload)
            elif command.type == "bind_relation":
                data = self._bind_relation(payload)
            elif command.type == "unbind_relation":
                data = self._unbind_relation(payload)
            elif command.type == "snap_to_slots":
                data = self._snap_to_slots(payload)
            else:
                raise ValueError(f"不支持的命令类型: {command.type}")
            return CommandResult(command.command_id, True, self.model.tick, data=data)
        except Exception as exc:
            return CommandResult(command.command_id, False, self.model.tick, error=str(exc))

    def advance(self, steps: int = 1, *, force: bool = False) -> list[CommandResult]:
        """处理排队命令，并在 playing 或 force 时推进模型。"""
        with self._lock:
            results = self.process_commands()
            if self.playing or force:
                for _ in range(max(1, int(steps))):
                    self.model.step()
            return results

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            result = self.model.export_snapshot(self.projection, format="dict")
            assert isinstance(result, dict)
            return result

    def next_message(self, *, prefer_delta: bool = False) -> dict[str, Any]:
        """生成下一条 snapshot 或基于上一快照的 delta。"""
        current = self.snapshot()
        if prefer_delta and self._previous_snapshot is not None:
            message = diff_snapshots(self._previous_snapshot, current)
        else:
            message = current
        self._previous_snapshot = current
        return message
