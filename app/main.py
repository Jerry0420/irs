"""FastAPI 入口：REST API、WebSocket 端點、靜態檔與圖片上傳。"""

import io
import uuid
from pathlib import Path

import segno
from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from .state import AppState, Pin, QuestionIn
from .ws import ConnectionManager

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
ADMIN_PASSWORD = "0000"  # 後台管理密碼（寫死於伺服器）
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
}

app = FastAPI(title="IRS 線上即時回饋系統")
state = AppState()
manager = ConnectionManager()

app.mount("/static", StaticFiles(directory=PUBLIC), name="static")
app.mount("/uploads", StaticFiles(directory=state.uploads_dir), name="uploads")


@app.middleware("http")
async def no_cache_assets(request, call_next):
    """強制瀏覽器每次重新整理都向伺服器驗證（ETag 304），避免改版後跑到舊 JS/CSS。"""
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/static/", "/uploads/")) or path in ("/", "/admin"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_as_400(_request, exc: RequestValidationError):
    detail = [
        {"loc": [str(x) for x in e.get("loc", [])], "msg": e.get("msg", "")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=400, content={"detail": detail})


def _vote_update_message(
    question_id: str, new_pins: list[dict], removed_pin_ids: list[str]
) -> dict | None:
    q = state.get(question_id)
    if not q:
        return None
    return {
        "type": "vote:update",
        "payload": {
            "questionId": q.id,
            "round": q.round,
            "votes": q.votes,
            "newPins": new_pins,
            "removedPinIds": removed_pin_ids,
        },
    }


manager.set_flush_payload_builder(_vote_update_message)


def _question_payload(q, include_results: bool = True) -> dict:
    """題目公開資料 + 題號（依目前排序）與總題數。

    觀眾端（include_results=False）不需要即時結果，剔除 votes/pins 減少推送量。
    """
    p = q.public()
    p["number"] = next((i + 1 for i, x in enumerate(state.questions) if x.id == q.id), None)
    p["total"] = len(state.questions)
    if not include_results:
        p.pop("votes", None)
        p.pop("pins", None)
    return p


def _state_init_payload(role: str) -> dict:
    q = state.active
    return {
        "type": "state:init",
        "payload": {
            "activeQuestionId": state.active_question_id,
            "question": _question_payload(q, include_results=(role == "admin")) if q else None,
        },
    }


async def _broadcast_question_event(msg_type: str, q, extra: dict | None = None) -> None:
    """向兩種角色各推一份題目訊息：後台含結果數據、觀眾端不含。"""
    for role in ("admin", "voter"):
        payload = {"question": _question_payload(q, include_results=(role == "admin"))}
        if extra:
            payload.update(extra)
        await manager.broadcast({"type": msg_type, "payload": payload}, only_role=role)


# ---------- 頁面 ----------


@app.get("/", include_in_schema=False)
async def vote_page():
    return FileResponse(PUBLIC / "vote.html")


@app.get("/admin", include_in_schema=False)
async def admin_page():
    return FileResponse(PUBLIC / "admin.html")


# ---------- 後台驗證 ----------


def require_admin(x_admin_token: str = Header(default="")):
    if x_admin_token != ADMIN_PASSWORD:
        raise HTTPException(401, "需要管理者密碼")


class LoginIn(BaseModel):
    password: str


@app.post("/api/admin/login")
async def admin_login(data: LoginIn):
    if data.password != ADMIN_PASSWORD:
        raise HTTPException(401, "密碼錯誤")
    return {"ok": True}


# ---------- REST API（後台用） ----------


@app.get("/api/questions")
async def list_questions():
    return {
        "questions": [q.public() for q in state.questions],
        "activeQuestionId": state.active_question_id,
    }


@app.post("/api/questions", status_code=201, dependencies=[Depends(require_admin)])
async def create_question(data: QuestionIn):
    q = state.create(data)
    await manager.broadcast({"type": "questions:changed", "payload": {}}, only_role="admin")
    return q.public()


@app.put("/api/questions/{question_id}", dependencies=[Depends(require_admin)])
async def update_question(question_id: str, data: QuestionIn):
    q = state.update(question_id, data)
    if not q:
        raise HTTPException(404, "question not found")
    await manager.broadcast({"type": "questions:changed", "payload": {}}, only_role="admin")
    if question_id == state.active_question_id:
        await _broadcast_question_event("question:switch", q)
    return q.public()


@app.delete("/api/questions/{question_id}", dependencies=[Depends(require_admin)])
async def delete_question(question_id: str):
    was_active = question_id == state.active_question_id
    if not state.delete(question_id):
        raise HTTPException(404, "question not found")
    await manager.broadcast({"type": "questions:changed", "payload": {}}, only_role="admin")
    if was_active:
        await manager.broadcast(
            {"type": "question:switch", "payload": {"question": None}}
        )
    return {"ok": True}


class ReorderIn(BaseModel):
    ids: list[str]


@app.post("/api/questions/reorder", dependencies=[Depends(require_admin)])
async def reorder_questions(data: ReorderIn):
    if not state.reorder(data.ids):
        raise HTTPException(400, "ids 必須恰為現有題目 id 的排列")
    await manager.broadcast({"type": "questions:changed", "payload": {}}, only_role="admin")
    # 排序改變會影響題號，若有進行中題目則同步更新各端顯示
    if state.active:
        await _broadcast_question_event("question:switch", state.active)
    return {"ok": True}


@app.post("/api/questions/{question_id}/activate", dependencies=[Depends(require_admin)])
async def activate_question(question_id: str):
    q = state.activate(question_id)
    if not q:
        raise HTTPException(404, "question not found")
    await _broadcast_question_event("question:switch", q)
    return {"ok": True, "activeQuestionId": question_id}


@app.post("/api/questions/{question_id}/reset", dependencies=[Depends(require_admin)])
async def reset_question(question_id: str):
    q = state.reset(question_id)
    if not q:
        raise HTTPException(404, "question not found")
    await _broadcast_question_event("vote:reset", q,
                                    extra={"questionId": q.id, "round": q.round})
    return {"ok": True, "round": q.round}


@app.post("/api/upload", dependencies=[Depends(require_admin)])
async def upload_image(file: UploadFile = File(...)):
    ext = ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if not ext:
        raise HTTPException(400, "僅接受 png / jpg / webp / svg 圖片")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "圖片大小不可超過 2MB")
    name = f"{uuid.uuid4().hex}{ext}"
    (state.uploads_dir / name).write_bytes(content)
    return {"url": f"/uploads/{name}"}


@app.get("/api/qrcode")
async def qrcode_svg(text: str = Query(..., max_length=500)):
    qr = segno.make(text, error="m")
    # 需輸出含 xmlns 的完整 SVG 文件，<img> 才能載入（svg_inline 片段會被瀏覽器拒繪）
    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=6, dark="#3E2723", light=None)
    return Response(buf.getvalue(), media_type="image/svg+xml")


# ---------- WebSocket ----------


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    role = "admin" if ws.query_params.get("role") == "admin" else "voter"
    await manager.connect(ws, role)
    try:
        await ws.send_json(_state_init_payload(role))
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")
            if msg_type == "vote:cast":
                await _handle_vote(ws, msg.get("payload") or {})
            elif msg_type == "vote:cancel":
                await _handle_cancel(ws, msg.get("payload") or {})
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def _handle_vote(ws: WebSocket, payload: dict) -> None:
    question_id = payload.get("questionId", "")
    option_id = payload.get("optionId", "")
    voter_id = str(payload.get("voterId") or "").strip()
    if not voter_id:
        await ws.send_json(
            {"type": "vote:rejected", "payload": {"reason": "missing_voter"}}
        )
        return
    pin = None
    if payload.get("pin") is not None:
        try:
            pin = Pin(option_id=option_id, **payload["pin"])
        except (ValidationError, TypeError):
            await ws.send_json(
                {"type": "vote:rejected", "payload": {"reason": "invalid_pin"}}
            )
            return

    ok, reason, new_pin = state.cast_vote(question_id, option_id, voter_id, pin)
    if not ok:
        await ws.send_json({"type": "vote:rejected", "payload": {"reason": reason}})
        return

    q = state.get(question_id)
    await ws.send_json(
        {
            "type": "vote:accepted",
            "payload": {
                "questionId": question_id,
                "round": q.round,
            },
        }
    )
    manager.queue_vote_update(question_id, new_pin.model_dump() if new_pin else None)


async def _handle_cancel(ws: WebSocket, payload: dict) -> None:
    question_id = payload.get("questionId", "")
    voter_id = str(payload.get("voterId") or "").strip()
    ok, reason, removed_pin_id = state.cancel_vote(question_id, voter_id)
    if not ok:
        await ws.send_json({"type": "cancel:rejected", "payload": {"reason": reason}})
        return
    q = state.get(question_id)
    await ws.send_json(
        {
            "type": "vote:cancelled",
            "payload": {
                "questionId": question_id,
                "round": q.round,
            },
        }
    )
    manager.queue_vote_update(question_id, removed_pin_id=removed_pin_id)
