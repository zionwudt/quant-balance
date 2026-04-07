"""WebSocket 实时推送端点。

支持事件类型：
- signal_new: 新信号生成
- paper_trade: 模拟盘成交
- equity_update: 权益变动
- scan_complete: 扫描完成
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])

# ── 连接管理 ──

_connections: set[WebSocket] = set()
_event_loop: asyncio.AbstractEventLoop | None = None


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket 连接端点，客户端连接后自动接收推送事件。"""
    from quant_balance.api.deps import load_api_key
    global _event_loop  # noqa: PLW0603

    api_key = load_api_key()
    if api_key is not None:
        token = websocket.query_params.get("token", "")
        if token != api_key:
            await websocket.close(code=4001)
            return

    await websocket.accept()
    _event_loop = asyncio.get_running_loop()
    _connections.add(websocket)
    try:
        while True:
            # 保持连接活跃，接收客户端心跳
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _connections.discard(websocket)


async def broadcast_event(event_type: str, payload: dict[str, Any]) -> None:
    """向所有已连接客户端广播事件。"""
    if not _connections:
        return
    message = json.dumps(
        {"type": event_type, "data": payload},
        ensure_ascii=False,
        default=str,
    )
    disconnected: set[WebSocket] = set()
    for ws in _connections:
        try:
            await ws.send_text(message)
        except Exception:  # noqa: BLE001
            disconnected.add(ws)
    _connections.difference_update(disconnected)


def notify_event(event_type: str, payload: dict[str, Any]) -> None:
    """同步接口：在非 async 上下文中触发广播（如调度器回调）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        loop.create_task(broadcast_event(event_type, payload))
        return

    target_loop = _event_loop
    if (
        target_loop is None
        or target_loop.is_closed()
        or not target_loop.is_running()
    ):
        return

    asyncio.run_coroutine_threadsafe(
        broadcast_event(event_type, payload),
        target_loop,
    )


__all__ = ["router", "broadcast_event", "notify_event"]
