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
                indices = self._indices_for_uids(kind, payload.get("uids", []))
                self.model.kill(kind, indices)
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
