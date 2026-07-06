"""後端 API 與投票邏輯測試：CRUD、切題、計票、取消重投、清除數據、WebSocket 廣播。"""


def get_state(client):
    res = client.get("/api/questions")
    assert res.status_code == 200
    return res.json()


def text_payload(title="測試題", labels=("甲", "乙", "丙")):
    return {"title": title, "type": "text",
            "options": [{"label": l} for l in labels]}


def image_payload(title="圖片題"):
    return {"title": title, "type": "image4",
            "options": [{"label": f"情景{i}", "image_url": f"/static/img/scene{i}.svg"}
                        for i in range(1, 5)]}


def cast(ws, question_id, option_id, voter="voter-1", pin=None):
    ws.send_json({"type": "vote:cast", "payload": {
        "questionId": question_id, "optionId": option_id,
        "voterId": voter, "pin": pin}})


def recv_type(ws, expected):
    msg = ws.receive_json()
    assert msg["type"] == expected, f"expected {expected}, got {msg}"
    return msg["payload"]


# ---------- 種子資料 ----------

def test_seed_questions(client):
    data = get_state(client)
    assert len(data["questions"]) == 4
    assert data["activeQuestionId"] == data["questions"][0]["id"]
    types = [q["type"] for q in data["questions"]]
    assert types.count("text") == 2 and types.count("image4") == 2


# ---------- CRUD ----------

def test_crud_flow(client):
    res = client.post("/api/questions", json=text_payload("新題目", ("是", "否")))
    assert res.status_code == 201
    q = res.json()
    assert q["title"] == "新題目" and len(q["options"]) == 2

    res = client.put(f"/api/questions/{q['id']}",
                     json=text_payload("改過的題目", ("A", "B", "C", "D", "E")))
    assert res.status_code == 200
    assert res.json()["title"] == "改過的題目"
    assert len(res.json()["options"]) == 5

    assert client.delete(f"/api/questions/{q['id']}").status_code == 200
    assert client.delete(f"/api/questions/{q['id']}").status_code == 404
    assert client.put("/api/questions/nope", json=text_payload()).status_code == 404


def test_image4_labels_optional(client):
    payload = image_payload("無說明圖題")
    for o in payload["options"]:
        o["label"] = ""
    res = client.post("/api/questions", json=payload)
    assert res.status_code == 201
    assert all(o["label"] == "" for o in res.json()["options"])
    client.delete(f"/api/questions/{res.json()['id']}")


def test_validation_errors(client):
    bad = [
        text_payload(labels=("只有一個",)),               # 文字題 < 2 選項
        {**image_payload(), "options": image_payload()["options"][:3]},  # 圖片題 != 4
        text_payload(title="   "),                        # 空題幹
        {"title": "x", "type": "image4",                  # 圖片題缺圖片
         "options": [{"label": str(i)} for i in range(4)]},
    ]
    for payload in bad:
        assert client.post("/api/questions", json=payload).status_code == 400


# ---------- 切題 ----------

def test_activate(client):
    data = get_state(client)
    second = data["questions"][1]["id"]
    assert client.post(f"/api/questions/{second}/activate").status_code == 200
    assert get_state(client)["activeQuestionId"] == second
    assert client.post("/api/questions/nope/activate").status_code == 404


def test_reorder(client):
    data = get_state(client)
    ids = [q["id"] for q in data["questions"]]
    res = client.post("/api/questions/reorder", json={"ids": ids[::-1]})
    assert res.status_code == 200
    assert [q["id"] for q in get_state(client)["questions"]] == ids[::-1]

    # ids 不完整或含不存在 id → 400
    assert client.post("/api/questions/reorder", json={"ids": ids[:2]}).status_code == 400
    assert client.post("/api/questions/reorder",
                       json={"ids": ids[:-1] + ["nope"]}).status_code == 400


def test_delete_active_clears_active(client):
    data = get_state(client)
    active = data["activeQuestionId"]
    client.delete(f"/api/questions/{active}")
    assert get_state(client)["activeQuestionId"] is None


# ---------- 投票（WebSocket） ----------

def test_vote_and_duplicate_rejected(client):
    data = get_state(client)
    q = data["questions"][0]
    oid = q["options"][0]["id"]

    with client.websocket_connect("/ws") as ws:
        init = recv_type(ws, "state:init")
        assert init["question"]["id"] == q["id"]
        assert init["question"]["number"] == 1          # 題號（依排序）
        assert init["question"]["total"] == len(data["questions"])

        cast(ws, q["id"], oid)
        recv_type(ws, "vote:accepted")
        update = recv_type(ws, "vote:update")
        assert update["votes"][oid] == 1

        cast(ws, q["id"], oid)
        assert recv_type(ws, "vote:rejected")["reason"] == "already_voted"


def test_same_voter_rejected_across_connections(client):
    """同一位觀眾（voterId）換連線（如重新整理）仍不能重複投票。"""
    data = get_state(client)
    q = data["questions"][0]
    oid = q["options"][0]["id"]

    with client.websocket_connect("/ws") as a:
        recv_type(a, "state:init")
        cast(a, q["id"], oid, voter="voter-x")
        recv_type(a, "vote:accepted")
        recv_type(a, "vote:update")

    with client.websocket_connect("/ws") as b:
        recv_type(b, "state:init")
        cast(b, q["id"], oid, voter="voter-x")
        assert recv_type(b, "vote:rejected")["reason"] == "already_voted"


def test_vote_requires_voter_id(client):
    data = get_state(client)
    q = data["questions"][0]
    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        ws.send_json({"type": "vote:cast", "payload": {
            "questionId": q["id"], "optionId": q["options"][0]["id"]}})
        assert recv_type(ws, "vote:rejected")["reason"] == "missing_voter"


def test_vote_rejected_when_not_active(client):
    data = get_state(client)
    inactive = data["questions"][1]
    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        cast(ws, inactive["id"], inactive["options"][0]["id"])
        assert recv_type(ws, "vote:rejected")["reason"] == "not_active"


def test_image4_pin_validation(client):
    data = get_state(client)
    q = next(x for x in data["questions"] if x["type"] == "image4")
    oid = q["options"][0]["id"]
    client.post(f"/api/questions/{q['id']}/activate")

    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")

        cast(ws, q["id"], oid, pin={"x": 1.5, "y": 0.5})   # 座標超出 0~1
        assert recv_type(ws, "vote:rejected")["reason"] == "invalid_pin"

        cast(ws, q["id"], oid)                              # 圖片題沒帶 pin
        assert recv_type(ws, "vote:rejected")["reason"] == "pin_required"

        cast(ws, q["id"], oid, pin={"x": 0.25, "y": 0.75})  # 合法投票
        recv_type(ws, "vote:accepted")
        update = recv_type(ws, "vote:update")
        assert update["votes"][oid] == 1
        (np,) = update["newPins"]
        assert np["option_id"] == oid and np["x"] == 0.25 and np["y"] == 0.75
        assert np["id"]


# ---------- 取消投票 / 重新投票 ----------

def test_cancel_vote_and_revote(client):
    data = get_state(client)
    q = data["questions"][0]
    oid_a, oid_b = q["options"][0]["id"], q["options"][1]["id"]

    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        cast(ws, q["id"], oid_a)
        recv_type(ws, "vote:accepted")
        recv_type(ws, "vote:update")

        ws.send_json({"type": "vote:cancel", "payload": {
            "questionId": q["id"], "voterId": "voter-1"}})
        recv_type(ws, "vote:cancelled")
        update = recv_type(ws, "vote:update")
        assert update["votes"][oid_a] == 0

        cast(ws, q["id"], oid_b)   # 取消後可改投其他選項
        recv_type(ws, "vote:accepted")
        update = recv_type(ws, "vote:update")
        assert update["votes"][oid_b] == 1


def test_cancel_without_vote_rejected(client):
    data = get_state(client)
    q = data["questions"][0]
    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        ws.send_json({"type": "vote:cancel", "payload": {
            "questionId": q["id"], "voterId": "nobody"}})
        assert recv_type(ws, "cancel:rejected")["reason"] == "not_voted"


def test_cancel_image4_removes_pin(client):
    data = get_state(client)
    q = next(x for x in data["questions"] if x["type"] == "image4")
    oid = q["options"][1]["id"]
    client.post(f"/api/questions/{q['id']}/activate")

    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        cast(ws, q["id"], oid, pin={"x": 0.5, "y": 0.5})
        recv_type(ws, "vote:accepted")
        pin_id = recv_type(ws, "vote:update")["newPins"][0]["id"]

        ws.send_json({"type": "vote:cancel", "payload": {
            "questionId": q["id"], "voterId": "voter-1"}})
        recv_type(ws, "vote:cancelled")
        update = recv_type(ws, "vote:update")
        assert update["votes"][oid] == 0
        assert update["removedPinIds"] == [pin_id]

    assert get_state(client)  # 伺服器狀態仍健康


# ---------- 清除數據 / 重新投票 ----------

def test_reset_clears_votes_and_allows_revote(client):
    data = get_state(client)
    q = data["questions"][0]
    oid = q["options"][0]["id"]

    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        cast(ws, q["id"], oid)
        recv_type(ws, "vote:accepted")
        recv_type(ws, "vote:update")

        res = client.post(f"/api/questions/{q['id']}/reset")
        assert res.status_code == 200 and res.json()["round"] == q["round"] + 1

        payload = recv_type(ws, "vote:reset")
        assert payload["question"]["votes"] == {} and payload["question"]["pins"] == []

        # 新一輪：同一位觀眾可以再投
        cast(ws, q["id"], oid)
        recv_type(ws, "vote:accepted")


# ---------- 廣播 ----------

def test_broadcast_between_clients(client):
    data = get_state(client)
    q = data["questions"][0]
    oid = q["options"][1]["id"]

    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        recv_type(a, "state:init")
        recv_type(b, "state:init")

        # A 投票，B 收到 vote:update
        cast(a, q["id"], oid, voter="voter-a")
        recv_type(a, "vote:accepted")
        assert recv_type(b, "vote:update")["votes"][oid] == 1
        recv_type(a, "vote:update")

        # 主持人切題，兩邊都收到 question:switch
        target = data["questions"][2]["id"]
        client.post(f"/api/questions/{target}/activate")
        assert recv_type(a, "question:switch")["question"]["id"] == target
        assert recv_type(b, "question:switch")["question"]["id"] == target


# ---------- 儲存分離：題目入版控、票數不入 ----------

def test_votes_stored_outside_questions_file(client):
    import json as _json
    from app import main as appmain

    data = get_state(client)
    q = data["questions"][0]
    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        cast(ws, q["id"], q["options"][0]["id"])
        recv_type(ws, "vote:accepted")
        recv_type(ws, "vote:update")

    appmain.state._write()  # 立即落盤（略過 debounce）
    qraw = _json.loads(appmain.state.file.read_text(encoding="utf-8"))
    assert all("votes" not in x and "pins" not in x and "voters" not in x
               for x in qraw["questions"])          # 題目檔不含任何投票結果
    assert "active_question_id" not in qraw          # 切題也不會弄髒題目檔

    rraw = _json.loads(appmain.state.results_file.read_text(encoding="utf-8"))
    assert sum(rraw["results"][q["id"]]["votes"].values()) == 1


def test_results_survive_reload(client):
    from app import main as appmain

    data = get_state(client)
    q = data["questions"][0]
    oid = q["options"][0]["id"]
    with client.websocket_connect("/ws") as ws:
        recv_type(ws, "state:init")
        cast(ws, q["id"], oid)
        recv_type(ws, "vote:accepted")
        recv_type(ws, "vote:update")

    appmain.state._write()
    appmain.state.load()   # 模擬重啟：題目與票數都要還原
    restored = appmain.state.get(q["id"])
    assert restored.votes.get(oid) == 1
    assert "voter-1" in restored.voters


# ---------- 後台驗證 ----------

def test_admin_login(client):
    assert client.post("/api/admin/login", json={"password": "0000"}).status_code == 200
    assert client.post("/api/admin/login", json={"password": "1234"}).status_code == 401


def test_admin_apis_require_password(client):
    bad = {"X-Admin-Token": "wrong"}
    q = get_state(client)["questions"][0]
    assert client.post("/api/questions", json=text_payload(), headers=bad).status_code == 401
    assert client.put(f"/api/questions/{q['id']}", json=text_payload(), headers=bad).status_code == 401
    assert client.delete(f"/api/questions/{q['id']}", headers=bad).status_code == 401
    assert client.post(f"/api/questions/{q['id']}/activate", headers=bad).status_code == 401
    assert client.post(f"/api/questions/{q['id']}/reset", headers=bad).status_code == 401
    assert client.post("/api/questions/reorder", json={"ids": []}, headers=bad).status_code == 401
    assert client.post("/api/upload", headers=bad,
                       files={"file": ("p.png", b"x", "image/png")}).status_code == 401
    # 觀眾用的讀取與投票不受影響
    assert client.get("/api/questions", headers=bad).status_code == 200


# ---------- 其他端點 ----------

def test_pages_and_qrcode(client):
    assert client.get("/").status_code == 200
    assert client.get("/admin").status_code == 200
    assert client.get("/display").status_code == 404   # 投影已併入後台，獨立頁面移除
    res = client.get("/api/qrcode", params={"text": "http://example.com/"})
    assert res.status_code == 200
    assert "svg" in res.headers["content-type"]
    # 必須是含 xmlns 的完整 SVG 文件，<img src> 才能顯示
    assert b'xmlns="http://www.w3.org/2000/svg"' in res.content


def test_voters_not_exposed_in_api(client):
    data = get_state(client)
    assert all("voters" not in q for q in data["questions"])


def test_upload_rejects_bad_type(client):
    res = client.post("/api/upload",
                      files={"file": ("x.txt", b"hello", "text/plain")})
    assert res.status_code == 400


def upload_png(client):
    png = (b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    res = client.post("/api/upload", files={"file": ("p.png", png, "image/png")})
    assert res.status_code == 200
    return res.json()["url"]


def image_payload_with(url, title="上傳圖題"):
    p = image_payload(title)
    p["options"][0]["image_url"] = url
    return p


def test_upload_accepts_png(client):
    url = upload_png(client)
    assert url.startswith("/uploads/") and url.endswith(".png")
    assert client.get(url).status_code == 200


def test_delete_question_removes_uploads(client):
    url = upload_png(client)
    q = client.post("/api/questions", json=image_payload_with(url)).json()
    assert client.get(url).status_code == 200

    client.delete(f"/api/questions/{q['id']}")
    assert client.get(url).status_code == 404          # 檔案已隨題目刪除


def test_delete_question_keeps_shared_uploads(client):
    url = upload_png(client)
    q1 = client.post("/api/questions", json=image_payload_with(url, "題一")).json()
    client.post("/api/questions", json=image_payload_with(url, "題二"))

    client.delete(f"/api/questions/{q1['id']}")
    assert client.get(url).status_code == 200          # 另一題仍引用，不可刪


def test_create_sweeps_replaced_upload(client):
    """建題表單中先上傳 A 再換成 B，儲存後 A 應被清除。"""
    url_a, url_b = upload_png(client), upload_png(client)
    client.post("/api/questions", json=image_payload_with(url_b))
    assert client.get(url_a).status_code == 404
    assert client.get(url_b).status_code == 200


def test_update_question_removes_replaced_upload(client):
    old_url = upload_png(client)
    q = client.post("/api/questions", json=image_payload_with(old_url)).json()
    new_url = upload_png(client)  # 依真實流程：編輯表單時才上傳新圖

    res = client.put(f"/api/questions/{q['id']}", json=image_payload_with(new_url))
    assert res.status_code == 200
    assert client.get(old_url).status_code == 404      # 被換掉的舊圖已清除
    assert client.get(new_url).status_code == 200
