import asyncio
import json
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger("ML.WebSocket")


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._connections.append(ws)
        logger.info(f"WebSocket 客户端已连接, 当前连接数: {len(self._connections)}")

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._connections:
                self._connections.remove(ws)
        logger.info(f"WebSocket 客户端已断开, 当前连接数: {len(self._connections)}")

    async def broadcast(self, message: dict[str, Any]):
        dead: list[WebSocket] = []
        async with self._lock:
            for ws in self._connections:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._connections.remove(ws)

    async def broadcast_console(self, line: str, timestamp: str = ""):
        await self.broadcast({
            "type": "console",
            "line": line,
            "timestamp": timestamp,
        })

    async def broadcast_status(self, status: dict[str, Any]):
        await self.broadcast({
            "type": "status",
            "data": status,
        })

    async def broadcast_network_status(self, status: dict[str, Any]):
        await self.broadcast({
            "type": "network_status",
            "data": status,
        })

    async def broadcast_notification(self, level: str, message: str):
        await self.broadcast({
            "type": "notification",
            "level": level,
            "message": message,
        })

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = WebSocketManager()
