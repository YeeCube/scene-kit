"""基于可选 ``websockets`` 依赖的本地交互服务器。"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from typing import Any

from scene_kit.runner import ModelSession


class WebSocketModelServer:
    """通过 WebSocket 暴露 ModelSession。

    服务器消息使用 ``hello``、``snapshot``、``delta``、``commandResult`` 和
    ``error`` envelope。模型状态仍由 WorldSnapshot/WorldDelta 表达。
    """

    def __init__(
        self,
        session: ModelSession,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        push_hz: float = 10.0,
        prefer_delta: bool = False,
    ) -> None:
        self.session = session
        self.host = host
        self.port = int(port)
        self.push_hz = float(push_hz)
        self.prefer_delta = prefer_delta
        self._clients: set[Any] = set()
        self._stop = asyncio.Event()

    @staticmethod
    def _envelope(message_type: str, payload: Any) -> str:
        return json.dumps(
            {"type": message_type, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    async def _send_state(self, websocket: Any, *, prefer_delta: bool = False) -> None:
        message = self.session.next_message(prefer_delta=prefer_delta)
        message_type = "delta" if message.get("protocol") == "wmk.world-delta" else "snapshot"
        await websocket.send(self._envelope(message_type, message))

    async def _handler(self, websocket: Any) -> None:
        self._clients.add(websocket)
        try:
            await websocket.send(self._envelope("hello", self.session.describe()))
            await self._send_state(websocket)
            async for raw in websocket:
                try:
                    request = json.loads(raw)
                    request_type = request.get("type")
                    if request_type == "getSnapshot":
                        await self._send_state(websocket)
                    elif request_type == "command":
                        result = self.session.dispatch(request.get("payload", {}))
                        await websocket.send(self._envelope("commandResult", result.to_dict()))
                        await self.broadcast_state()
                    else:
                        raise ValueError(f"未知消息类型: {request_type}")
                except Exception as exc:
                    await websocket.send(self._envelope("error", {"message": str(exc)}))
        finally:
            self._clients.discard(websocket)

    async def broadcast_state(self) -> None:
        if not self._clients:
            return
        message = self.session.next_message(prefer_delta=self.prefer_delta)
        message_type = "delta" if message.get("protocol") == "wmk.world-delta" else "snapshot"
        encoded = self._envelope(message_type, message)
        stale: list[Any] = []
        for client in tuple(self._clients):
            try:
                await client.send(encoded)
            except Exception:
                stale.append(client)
        for client in stale:
            self._clients.discard(client)

    async def _producer(self) -> None:
        while not self._stop.is_set():
            if self.session.playing:
                self.session.advance()
                await self.broadcast_state()
                interval = 1.0 / max(self.session.rate, 0.1)
            else:
                interval = 1.0 / max(self.push_hz, 1.0)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except TimeoutError:
                pass

    async def serve_forever(self) -> None:
        try:
            from websockets.asyncio.server import serve
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("启动 WebSocket 服务需要安装 scene-kit[server]") from exc
        async with serve(self._handler, self.host, self.port):
            producer = asyncio.create_task(self._producer())
            try:
                await self._stop.wait()
            finally:
                producer.cancel()
                with suppress(asyncio.CancelledError):
                    await producer

    def stop(self) -> None:
        self._stop.set()


async def serve_session(
    session: ModelSession,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    push_hz: float = 10.0,
) -> None:
    """便捷入口：持续服务一个 ModelSession。"""
    await WebSocketModelServer(session, host=host, port=port, push_hz=push_hz).serve_forever()
