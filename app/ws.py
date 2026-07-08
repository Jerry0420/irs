"""WebSocket 連線管理：廣播、vote:update 節流合併（含新增/移除的大頭針）。"""
import asyncio

from fastapi import WebSocket

BROADCAST_THROTTLE_SECONDS = 0.1


class ConnectionManager:
    def __init__(self):
        self._connections: dict[WebSocket, str] = {}       # ws -> 角色（admin / voter）
        self._pending_qids: set[str] = set()
        self._pending_pins: dict[str, list[dict]] = {}     # question_id -> 新增 pins
        self._pending_removed: dict[str, list[str]] = {}   # question_id -> 移除的 pin ids
        self._flush_task: asyncio.Task | None = None
        self._flush_payload = None  # 由 main 注入：(qid, new_pins, removed_ids) -> 訊息

    async def connect(self, ws: WebSocket, role: str = "voter") -> None:
        await ws.accept()
        self._connections[ws] = role

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.pop(ws, None)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast(self, message: dict, only_role: str | None = None) -> None:
        for ws, role in list(self._connections.items()):
            if only_role is not None and role != only_role:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)

    # ---------- vote:update 節流：100ms 內的投票/取消合併成一次廣播 ----------

    def set_flush_payload_builder(self, builder) -> None:
        """builder(question_id, new_pins, removed_pin_ids) -> vote:update 訊息 dict"""
        self._flush_payload = builder

    def queue_vote_update(self, question_id: str, new_pin: dict | None = None,
                          removed_pin_id: str | None = None) -> None:
        self._pending_qids.add(question_id)
        if new_pin is not None:
            self._pending_pins.setdefault(question_id, []).append(new_pin)
        if removed_pin_id is not None:
            self._pending_removed.setdefault(question_id, []).append(removed_pin_id)
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.get_running_loop().create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(BROADCAST_THROTTLE_SECONDS)
        qids, self._pending_qids = self._pending_qids, set()
        pins, self._pending_pins = self._pending_pins, {}
        removed, self._pending_removed = self._pending_removed, {}
        for qid in qids:
            message = self._flush_payload(qid, pins.get(qid, []), removed.get(qid, []))
            if message:
                # 即時票數/圖釘只推給後台（管理與投影頁），觀眾端不需要
                await self.broadcast(message, only_role="admin")
