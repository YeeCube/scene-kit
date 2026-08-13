"""demos 共用的命令行与 WebSocket 会话入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Callable, Mapping
from typing import Any

from scene_kit import ModelSession, WorldModel
from scene_kit.transport import serve_session


def demo_parser(description: str, *, default_ticks: int) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--ticks", type=int, default=default_ticks, help="无前端模式运行的 tick 数")
    parser.add_argument("--serve", action="store_true", help="启动 Studio 使用的 WebSocket 会话")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rate", type=float, default=10.0, help="交互会话每秒 tick 数")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=JSON",
        help="覆盖模型参数，例如 --set n_birds=500",
    )
    return parser


def parse_config(values: list[str]) -> dict[str, Any]:
    config: dict[str, Any] = {}
    for item in values:
        key, separator, raw = item.partition("=")
        if not separator or not key:
            raise ValueError(f"参数必须使用 KEY=JSON 格式: {item}")
        try:
            config[key] = json.loads(raw)
        except json.JSONDecodeError:
            config[key] = raw
    return config


def serve_demo(
    create_model: Callable[[Mapping[str, Any] | None], WorldModel],
    *,
    name: str,
    config: Mapping[str, Any],
    host: str,
    port: int,
    rate: float,
) -> None:
    session = ModelSession(
        create_model(config),
        model_factory=create_model,
        parameters=config,
        name=name,
    )
    session.rate = rate
    print(f"{name}: ws://{host}:{port}（在 frontend 运行 pnpm dev 后连接）")
    asyncio.run(serve_session(session, host=host, port=port, push_hz=rate))


def snapshot_entity_count(model: WorldModel) -> int:
    snapshot = model.export_snapshot(format="dict")
    assert isinstance(snapshot, dict)
    return sum(batch["count"] for batch in snapshot["entityBatches"].values())
