# 線上即時回饋系統（IRS）實作計畫

> 狀態：**待確認**（尚未動工，等待使用者核可）
> 日期：2026-07-06

---

## 1. 任務目標與非目標

### 1.1 目標

建立一套「現場即時回饋系統」，包含兩個網頁與一個即時同步後端：

| 頁面 | 路徑（規劃） | 對象 |
|------|-------------|------|
| 觀眾投票頁面 | `/` （`vote.html`） | 現場觀眾，手機瀏覽器 |
| 主持人後台管理頁面 | `/admin` （`admin.html`） | 主持人，免登入 |

**主持人後台功能**

1. 免註冊登入即可使用。
2. 題目與答案的 CRUD（新增、讀取、編輯、刪除）。
3. 同時顯示四道題目的即時票數數據與畫面縮小預覽。
4. 「切換題目」控制鈕 —— 切換時透過 WebSocket 廣播，觀眾端**即時自動同步**切換。
5. 「清除數據／重新投票」按鈕 —— 清空該題票數並解除觀眾端的已投票鎖定。

**題目與選項類型（題目皆為文字）**

| 類型 | 選項形式 | 投票結果呈現 |
|------|---------|-------------|
| A：文字題 | n 個文字選項（n ≥ 2，數量不限，後台可自由增減） | **文字雲**：得票越多的選項字體即時平滑放大，得票少的字體較小 |
| B：四格圖片題 | 四張圖片排成 2×2 格 | **圖片插針（Image Map with Pins）**：觀眾點擊圖片即完成投票，點擊處冒出大頭針/小紅點，票越多該區域大頭針越密集 |

**觀眾端功能**

1. 免註冊登入，輸入網址或掃 QR Code 即可進入（後台提供觀眾頁 QR Code）。
2. 手機優先（mobile-first）版面，按鈕與圖片點擊區域大（點擊目標 ≥ 44px）。
3. 每人每題限投一票：投票後鎖定畫面，顯示「投票成功，請等待下一題」；主持人切換題目或清除數據後自動解鎖。
4. 觀眾端即時看到文字雲縮放／大頭針浮現的動態結果。

**視覺風格（溫暖人文木質風）**

- 背景：柔和米白 `#F5F2EB`；主要文字與按鈕：深褐木質色 `#3E2723`。
- 字體：襯線體（Serif），如 `"Noto Serif TC", "Songti TC", "PMingLiU", serif`，營造紙質質感。
- 動態：文字雲縮放、大頭針出現皆使用 CSS `transition` / `animation` 平滑漸變。

### 1.2 非目標（本次不做）

- 不做帳號系統、權限驗證（後台僅以「不公開網址路徑」作弱保護）。
- 不做資料庫持久化（Server 記憶體 + 定期寫入 JSON 檔即可；重啟後題目保留、票數可接受重置）。
- 不做多場次／多房間（Room）支援，單一活動場次。
- 不做防刷票的強機制（僅以瀏覽器 `localStorage` + Socket session 做每題一票的軟性限制，不處理無痕視窗繞過）。
- 不做觀眾端國際化（i18n），介面為繁體中文。
- 不做正式雲端部署（HTTPS、網域、反向代理等）；執行環境為 **Docker 容器**（本機/區網），不支援容器外裸跑作為正式方式（僅開發測試用）。

---

## 2. 受影響檔案

專案目前為空專案（僅 `README.md`），以下皆為**新增**檔案：

```
irs/
├── Dockerfile                    # 新增：python:3.11-slim-bullseye 基底，安裝依賴、以 uvicorn 啟動
├── docker-compose.yml            # 新增：port 3000 映射、data/ 掛載為 volume（票題資料與上傳圖持久化）
├── .dockerignore                 # 新增：排除 .git、.venv、tests、docs 等
├── requirements.txt              # 新增：Python 依賴（fastapi, uvicorn, python-multipart 等，版本鎖定）
├── app/
│   ├── main.py                   # 新增：FastAPI 入口（REST API、WebSocket 端點、靜態檔掛載）
│   ├── state.py                  # 新增：伺服器狀態管理（題目、票數、voteRound、JSON 落盤）
│   └── ws.py                     # 新增：WebSocket 連線管理員（廣播、每連線投票去重）
├── data/
│   ├── questions.json            # 新增：題目資料持久化（含 4 道預設示範題）
│   └── uploads/                  # 新增：圖片題圖片上傳目錄（.gitkeep）
├── public/
│   ├── vote.html                 # 新增：觀眾投票頁
│   ├── admin.html                # 新增：主持人後台管理頁
│   ├── css/
│   │   └── style.css             # 新增：共用木質風主題（色調、襯線字體、transition 動畫）
│   ├── js/
│   │   ├── ws-client.js          # 新增：WebSocket 封裝（自動重連、重連後重新對齊狀態）
│   │   ├── vote.js               # 新增：觀眾端邏輯（連線、投票、鎖定、結果渲染）
│   │   ├── admin.js              # 新增：後台邏輯（CRUD、預覽、切題、清除數據）
│   │   ├── wordcloud.js          # 新增：文字雲渲染模組（依票數比例平滑縮放字級）
│   │   ├── pinmap.js             # 新增：圖片插針渲染模組（點擊座標 → Pin 動畫）
│   │   └── qrcode.min.js         # 新增：QR Code 產生（vendored 離線函式庫，避免依賴 CDN）
│   └── img/                      # 新增：預設示範圖片（4 張情境圖，圖片題用）
├── tests/
│   └── test_server.py            # 新增：後端 API 與投票邏輯測試（pytest + TestClient）
├── docs/
│   └── ai-plan.md                # 本文件
└── README.md                     # 修改：補上安裝、啟動、使用說明
```

技術選型：**Python FastAPI + 原生 WebSocket（uvicorn）**，前端為無框架的原生 HTML/CSS/JS。
理由：需求核心是「低延遲雙向即時同步」，FastAPI 原生支援 WebSocket 且與 REST API 同一個 app；無登入、無資料庫需求，不需要前端框架，維持零建置（no build step）。前端以 `ws-client.js` 薄封裝補上自動重連。

---

## 3. 修改步驟（可執行）

### 步驟 1：初始化專案與 Docker 環境

```bash
# 開發用虛擬環境（跑測試、IDE 補全用；正式執行走 Docker）
python3 -m venv .venv && source .venv/bin/activate
pip install fastapi "uvicorn[standard]" python-multipart pytest httpx
pip freeze > requirements.txt
```

撰寫 `Dockerfile`（`python:3.11-slim-bullseye` 基底——本機 Docker 20.10.7 的 seccomp 不支援 clone3，bookworm 基底會出現 "can't start new thread"、`pip install -r requirements.txt`、`EXPOSE 3000`、CMD 為 `uvicorn app.main:app --host 0.0.0.0 --port 3000`）、`.dockerignore`，以及 `docker-compose.yml`：

```yaml
services:
  irs:
    build: .
    ports: ["3000:3000"]
    volumes: ["./data:/app/data"]   # 題目 JSON 與上傳圖片持久化，容器重啟不遺失
    restart: unless-stopped
```

正式啟動指令：`docker compose up -d --build`

### 步驟 2：定義資料模型與伺服器狀態（`app/state.py`）

- 題目 schema（Pydantic model，兼作 API 驗證）：

  ```python
  class Option(BaseModel):
      id: str
      label: str
      image_url: str | None = None

  class Question(BaseModel):
      id: str                          # uuid
      title: str                       # 題目文字
      type: Literal["text", "image4"]  # 文字題（n 選項）/ 四格圖片題
      options: list[Option]            # text 長度 ≥ 2（不限上限）；image4 固定長度 4
      votes: dict[str, int]            # {option_id: 票數}
      pins: list[Pin]                  # image4 專用；Pin = {option_id, x, y}，x/y 為圖內相對座標 (0~1)
  ```

- 全域狀態：`{ questions: Question[], activeQuestionId: string|null, voteRound: number }`
  - `voteRound`：每次「清除數據」+1，觀眾端以 `questionId + voteRound` 為鍵記錄是否已投，據此實現「重新投票解鎖」。
- 啟動時讀取 `data/questions.json`（不存在則寫入 4 道預設示範題），變更時 debounce 寫回。

### 步驟 3：後端 API 與 WebSocket 事件（`app/main.py` + `app/ws.py`）

REST API（後台 CRUD 用）：

| Method | Path | 功能 |
|--------|------|------|
| GET    | `/api/questions` | 取得全部題目與即時票數 |
| POST   | `/api/questions` | 新增題目 |
| PUT    | `/api/questions/:id` | 編輯題目（題幹、選項、圖片） |
| DELETE | `/api/questions/:id` | 刪除題目 |
| POST   | `/api/questions/:id/activate` | 切換為目前題目 |
| POST   | `/api/questions/:id/reset` | 清除該題數據、voteRound+1 |
| POST   | `/api/upload` | 上傳圖片題圖片（multipart，限 png/jpg/webp ≤ 2MB） |

WebSocket 端點 `GET /ws`（觀眾與後台共用），訊息一律為 JSON `{"type": ..., "payload": ...}`：

| 訊息 type | 方向 | 內容 |
|------|------|------|
| `state:init` | server → client（連線時） | 目前題目、票數、pins、voteRound |
| `question:switch` | server → all | 主持人切題，觀眾端即時換頁 |
| `vote:cast` | client → server | `{ questionId, optionId, pin? }`，伺服器驗證後計票 |
| `vote:update` | server → all | 廣播最新票數與新增的 pin（後台與觀眾端同步刷新） |
| `vote:reset` | server → all | 清除數據，觀眾端解鎖重新投票 |

- `app/ws.py` 維護連線集合（ConnectionManager）負責廣播，並以連線層記錄「此連線在本輪已投過」，與前端 localStorage 雙重防重複。

### 步驟 4：木質風主題與共用樣式（`public/css/style.css`）

- CSS 變數：`--bg: #F5F2EB; --ink: #3E2723; --accent: #8D6E63;`
- 全站 `font-family: "Noto Serif TC", "Songti TC", "PMingLiU", Georgia, serif;`
- 按鈕：深褐底、米白字、圓角、`min-height: 56px`（手機大點擊區）。
- 動畫基礎：`transition: font-size .6s ease, transform .5s ease, opacity .5s ease;`
- 大頭針進場動畫：`@keyframes pin-drop`（由上落下 + 微彈跳 + 淡入）。

### 步驟 5：觀眾投票頁（`public/vote.html` + `vote.js`）

1. 透過 `ws-client.js` 連線 `/ws`（斷線自動指數退避重連，重連成功即重收 `state:init`），收 `state:init` / `question:switch` 渲染目前題目。
2. **text 題**：n 個全寬大按鈕直向排列（選項多時可捲動）；投票後按鈕區替換為文字雲結果視圖。
3. **image4 題**：2×2 格圖片，`touch/click` 取相對座標 (x, y) 送出 `vote:cast`；投票後圖上即時浮現所有觀眾的 pins。
4. 投票鎖定：送出成功後在 `localStorage` 記 `voted:{questionId}:{voteRound}`，顯示遮罩「投票成功，請等待下一題」；收到 `question:switch` 或 `vote:reset` 時依鍵值判斷是否解鎖。
5. 文字雲渲染（`wordcloud.js`）：字級 = `min + (max - min) × 該選項票數佔比`，靠 CSS transition 平滑縮放。
6. 插針渲染（`pinmap.js`）：pins 以百分比定位絕對疊在圖片上，新 pin 播放 `pin-drop` 動畫；響應式下座標不跑位。

### 步驟 6：主持人後台（`public/admin.html` + `admin.js`）

1. 題目列表（CRUD 表單）：新增／編輯（含選項與圖片上傳）／刪除，呼叫 REST API。
2. 四題即時儀表板：2×2 卡片，各卡片顯示題目、各選項票數長條、以及縮小版結果預覽（重用 `wordcloud.js` / `pinmap.js` 元件）。
3. 每張卡片上的「切換到此題」按鈕（目前題目高亮標示）與「清除數據／重新投票」按鈕（附 confirm 確認）。
4. 顯示觀眾頁網址 + QR Code（`qrcode.min.js` 本地產生，網址取 `location.origin`）。
5. 後台同樣訂閱 `vote:update`，數據即時跳動。

### 步驟 7：預設資料與示範圖

- `data/questions.json` 內建 4 道題（2 道 text —— 一道 2 選項、一道 5 選項以示範 n 選項，2 道 image4），`public/img/` 放 4 張示範情境圖（以本地產生的簡單佔位圖即可，不從外部下載）。

### 步驟 8：測試與文件

- 撰寫 `test/server.test.js`（詳見 §5）。
- 更新 `README.md`：Docker 啟動（`docker compose up -d --build`）、開發模式（venv + uvicorn `--reload`）、跑測試方式、後台/觀眾網址、區網手機連線說明（`http://<主機IP>:3000`）。

### 步驟 9：自我驗證後提交審閱

- 依 §5 執行測試與手動驗證，貼出結果，**不自動 commit**，等待使用者確認。

---

## 4. 風險與回滾方式

### 4.1 風險

| # | 風險 | 影響 | 緩解 |
|---|------|------|------|
| R1 | 免登入後台：知道 `/admin` 網址的任何人都能操作 | 現場可能被亂改題目 | 屬既定需求（非目標不做登入）；於 README 註明風險，後台路徑可改為帶隨機片段（如 `/admin-x7k2`） |
| R2 | localStorage 防重複投票可被無痕視窗繞過 | 票數可灌水 | 已列為非目標；伺服器端加 WebSocket 連線層去重降低誤觸，README 註明限制 |
| R3 | 伺服器記憶體存票數，容器重啟票數消失 | 活動中重啟會掉數據 | 題目與上傳圖經 volume（`./data`）落盤保留；票數屬活動當下數據，重啟即等同重新投票，主持人可接受（README 註明） |
| R4 | 大量觀眾同時投票時 `vote:update` 廣播頻繁 | 前端重繪卡頓 | 廣播端 throttle（≥100ms 合併一次），pins 僅增量傳送 |
| R5 | image4 的 pin 座標在不同螢幕尺寸下錯位 | 結果呈現失真 | 一律儲存 0~1 相對座標，以百分比定位渲染 |
| R6 | 手機瀏覽器休眠後 WebSocket 斷線 | 觀眾端畫面停格 | `ws-client.js` 指數退避自動重連 + 重連時重新收 `state:init` 對齊狀態 |
| R7 | 圖片上傳無限制導致磁碟被塞爆或上傳惡意檔 | 服務異常 | 限制 MIME（png/jpg/webp）與大小 ≤ 2MB，檔名改用 uuid |
| R8 | 主機埠 3000 被占用或 Docker 環境不可用 | 容器起不來 | compose 埠號集中一處易改；README 提供裸跑 uvicorn 的備援方式（開發測試用） |

### 4.2 回滾方式

- 本次全部為**新增檔案**，不動任何既有程式碼，回滾成本極低：
  1. 實作將在 feature branch（如 `feat/irs`）上進行，不合意直接不合併、刪除分支即可。
  2. 若已合入 `main`：`git revert <merge-commit>` 或 `git rm -r app/ public/ data/ tests/ requirements.txt Dockerfile docker-compose.yml .dockerignore` 一次移除。
  3. 停用服務：`docker compose down`（加 `--rmi local` 順帶清除映像），不留常駐程序。
  4. 執行期資料（`data/questions.json`、`data/uploads/`）不入版控（加入 `.gitignore`，僅保留預設種子檔），刪除目錄即還原。

---

## 5. 驗證方式（要跑哪些測試）

### 5.1 自動化測試（`pytest`）

`tests/test_server.py` 涵蓋（REST 用 FastAPI `TestClient`，WebSocket 用 `TestClient.websocket_connect`，無需額外依賴）：

1. **CRUD**：POST/GET/PUT/DELETE `/api/questions` 全流程；非法 payload（text 題選項 < 2、image4 題選項 ≠ 4、空題幹）回 400。
2. **切題**：`/activate` 後 GET 狀態的 `activeQuestionId` 正確；activate 不存在的 id 回 404。
3. **計票**：`vote:cast` 後票數 +1；同一 socket 對同題重複投被拒絕；image4 投票 pin 座標落在 0~1 範圍才接受。
4. **清除數據**：`/reset` 後票數歸零、pins 清空、`voteRound` 遞增。
5. **WebSocket 廣播**：以兩條 `websocket_connect` 連線，驗證 A 投票後 B 收到 `vote:update`、主持人 activate 後觀眾收到 `question:switch`。

### 5.2 手動驗證清單（開兩個瀏覽器視窗模擬）

```bash
docker compose up -d --build
# http://localhost:3000（觀眾）、http://localhost:3000/admin（後台）
```

- [ ] `docker compose up -d --build` 一鍵啟動成功，`docker compose logs` 無錯誤。
- [ ] `docker compose restart` 後題目與上傳圖片仍在（volume 持久化生效）。

- [ ] 後台可新增/編輯/刪除題目，四題卡片即時顯示票數與預覽。
- [ ] 後台按「切換題目」，觀眾端**不重新整理**即自動換題。
- [ ] text 題：兩人投不同選項，雙方畫面文字雲字級**平滑**變化；5 選項示範題在手機上按鈕仍夠大、排版不擠。
- [ ] image4 題：點圖後該處冒出帶動畫的大頭針，另一視窗同步看到。
- [ ] 投完票畫面鎖定顯示「投票成功，請等待下一題」；重新整理仍維持鎖定。
- [ ] 後台按「清除數據」，票數歸零、觀眾端解鎖可重投。
- [ ] 後台 QR Code 可掃描進入觀眾頁（區網手機實測）。
- [ ] 手機視窗（DevTools 模擬 iPhone）按鈕與圖片點擊區域夠大、無橫向捲動。
- [ ] 視覺檢查：米白底 `#F5F2EB`、深褐字 `#3E2723`、襯線字體、動畫平滑。

---

*本計畫核可後才會開始新增程式碼。*
