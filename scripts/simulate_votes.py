#!/usr/bin/env python3
"""模擬多位觀眾對「目前進行中的題目」投票，用於單機測試文字雲／插針效果。

用法（在專案根目錄）：
    .venv/bin/python scripts/simulate_votes.py            # 預設 30 票、每 0.8 秒一票
    .venv/bin/python scripts/simulate_votes.py 60 0.3     # 60 票、每 0.3 秒一票
    .venv/bin/python scripts/simulate_votes.py 60 0.5 8,2 # 指定各選項權重（依選項順序，比例 8:2）

投完後可在後台按「清除數據」還原該題。
"""
import asyncio
import json
import random
import sys
import uuid

import httpx
import websockets

BASE = "http://127.0.0.1:3000"


async def main(count: int, delay: float, fixed_weights: list[float] | None = None) -> None:
    async with httpx.AsyncClient(base_url=BASE) as api:
        data = (await api.get("/api/questions")).json()
        active = next((q for q in data["questions"]
                       if q["id"] == data["activeQuestionId"]), None)
        if not active:
            print("目前沒有進行中的題目，請先在後台切換一題。")
            return
        print(f"對「{active['title']}」（{active['type']}）投 {count} 票，間隔 {delay}s")

    # 各選項的抽中權重：可由第 3 個參數指定（如 8,2），未指定則隨機
    options = active["options"]
    if fixed_weights:
        if len(fixed_weights) != len(options):
            print(f"權重數量（{len(fixed_weights)}）需等於選項數（{len(options)}）")
            return
        weights = fixed_weights
    else:
        weights = [random.uniform(0.5, 3.0) for _ in options]
    for o, w in zip(options, weights):
        print(f"  權重 {w:g}：{o['label'] or '(無說明)'}")

    ws_url = BASE.replace("http", "ws", 1) + "/ws"
    async with websockets.connect(ws_url) as ws:
        await ws.recv()  # state:init
        for i in range(count):
            opt = random.choices(options, weights=weights)[0]
            payload = {
                "questionId": active["id"],
                "optionId": opt["id"],
                "voterId": f"sim-{uuid.uuid4().hex[:10]}",  # 每票一位虛擬觀眾
            }
            if active["type"] == "image4":
                payload["pin"] = {"x": round(random.uniform(.08, .92), 3),
                                  "y": round(random.uniform(.08, .85), 3)}
            await ws.send(json.dumps({"type": "vote:cast", "payload": payload}))
            while True:  # 略過 broadcast，等自己的回覆
                m = json.loads(await ws.recv())
                if m["type"] in ("vote:accepted", "vote:rejected"):
                    break
            print(f"[{i + 1}/{count}] {opt['label'] or '(無說明)'} ← {m['type']}")
            await asyncio.sleep(delay)

    print("完成。可在後台對該題按「清除數據」還原。")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    d = float(sys.argv[2]) if len(sys.argv) > 2 else 0.8
    w = [float(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else None
    asyncio.run(main(n, d, w))
