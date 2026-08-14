"""协议编码和本地传输的冒烟测试。"""

from __future__ import annotations

import asyncio
import json
import socket

import msgpack

from scene_kit import ModelSession
from scene_kit.transport.websocket import WebSocketModelServer
from tests.test_protocol import make_model


def test_snapshot_msgpack_roundtrip() -> None:
    snapshot = make_model().export_snapshot(format="dict")
    encoded = make_model().export_snapshot(format="msgpack")
    decoded = msgpack.unpackb(encoded, raw=False)
    assert decoded["protocol"] == snapshot["protocol"]
    assert decoded["entityBatches"]["particle"]["columns"]["uid"]


def test_server_accepts_ping_and_delta_configuration() -> None:
    server = WebSocketModelServer(ModelSession(make_model()), prefer_delta=True)
    assert server.prefer_delta is True
    assert server._envelope("pong", {"tick": 0}) == '{"type":"pong","payload":{"tick":0}}'
    asyncio.run(asyncio.sleep(0))


def test_websocket_session_smoke_roundtrip() -> None:
    async def scenario() -> None:
        import websockets

        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = int(probe.getsockname()[1])
        server = WebSocketModelServer(ModelSession(make_model(), model_factory=make_model), port=port, prefer_delta=True)
        task = asyncio.create_task(server.serve_forever())
        try:
            for _ in range(50):
                try:
                    connection = await websockets.connect(f"ws://127.0.0.1:{port}")
                    break
                except OSError:
                    await asyncio.sleep(0.01)
            else:
                raise AssertionError("WebSocket server did not start")
            async with connection:
                hello = json.loads(await connection.recv())
                snapshot = json.loads(await connection.recv())
                assert hello["type"] == "hello"
                assert snapshot["type"] == "snapshot"
                await connection.send(json.dumps({"type": "command", "payload": {"type": "step", "commandId": "smoke"}}))
                result = json.loads(await connection.recv())
                state = json.loads(await connection.recv())
                assert result["payload"]["accepted"] is True
                assert state["payload"]["tick"] == 1
        finally:
            server.stop()
            await task

    asyncio.run(scenario())
