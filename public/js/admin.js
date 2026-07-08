/* 主持人後台：題目 CRUD、即時數據儀表板、切題與清除數據 */
(() => {
  const $ = (id) => document.getElementById(id);
  const DEFAULT_IMAGES = [
    "/static/img/scene1.svg", "/static/img/scene2.svg",
    "/static/img/scene3.svg", "/static/img/scene4.svg",
  ];

  let questions = [];
  let activeId = null;
  let editingId = null; // null = 新增

  // ---------- 管理密碼 ----------

  const TOKEN_KEY = "irs-admin-token";
  const TOKEN_TS_KEY = "irs-admin-token-ts";
  const TOKEN_TTL_MS = 14 * 24 * 60 * 60 * 1000;  // 14 天後自動登出

  function adminToken() {
    const ts = parseInt(localStorage.getItem(TOKEN_TS_KEY) || "0", 10);
    if (!ts || Date.now() - ts > TOKEN_TTL_MS) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_TS_KEY);
      return "";
    }
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  async function verifyPassword(password) {
    const res = await fetch("/api/admin/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    return res.ok;
  }

  function showLogin() {
    $("login-backdrop").hidden = false;
    $("login-pass").focus();
  }

  async function ensureAuth() {
    const t = adminToken();
    if (t && (await verifyPassword(t))) return;   // 記在瀏覽器內，免再次輸入
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_TS_KEY);
    showLogin();
  }

  async function submitLogin() {
    const pass = $("login-pass").value;
    if (await verifyPassword(pass)) {
      localStorage.setItem(TOKEN_KEY, pass);
      localStorage.setItem(TOKEN_TS_KEY, String(Date.now()));
      $("login-backdrop").hidden = true;
      $("login-error").textContent = "";
      loadQuestions();
    } else {
      $("login-error").textContent = "密碼錯誤，請再試一次";
      $("login-pass").value = "";
      $("login-pass").focus();
    }
  }

  $("login-btn").addEventListener("click", submitLogin);
  $("login-pass").addEventListener("keydown", (e) => {
    if (e.key === "Enter") submitLogin();
  });
  ensureAuth();

  // ---------- API ----------

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      ...opts,
      headers: {
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
        "X-Admin-Token": adminToken(),
      },
    });
    if (res.status === 401) {   // 密碼失效（例如伺服器改了密碼）→ 重新要求輸入
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_TS_KEY);
      showLogin();
      throw new Error("需要管理者密碼");
    }
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        detail = typeof data.detail === "string" ? data.detail
          : (data.detail?.[0]?.msg || JSON.stringify(data.detail));
      } catch { /* keep default */ }
      throw new Error(detail);
    }
    return res.json();
  }

  async function loadQuestions() {
    const data = await api("/api/questions");
    questions = data.questions;
    activeId = data.activeQuestionId;
    renderCards();
    renderProjection();
  }

  // ---------- 儀表板卡片 ----------

  function renderCards() {
    const grid = $("cards");
    grid.innerHTML = "";
    questions.forEach((q, i) => grid.appendChild(buildCard(q, i)));
    if (!questions.length) {
      grid.innerHTML = '<div class="waiting">尚無題目，請點「新增題目」。</div>';
    }
  }

  async function moveQuestion(qid, delta) {
    const ids = questions.map((q) => q.id);
    const i = ids.indexOf(qid);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    await api("/api/questions/reorder", { method: "POST", body: JSON.stringify({ ids }) });
  }

  function buildCard(q, index) {
    const card = document.createElement("div");
    card.className = "q-card";
    card.dataset.qid = q.id;
    card.innerHTML = `
      <div class="q-head">
        <span class="q-num"></span>
        <span class="badge type"></span>
        <span class="badge live" hidden>進行中</span>
        <span class="spacer"></span>
        <span class="order-btns">
          <button class="order-btn act-up" title="上移">↑</button>
          <button class="order-btn act-down" title="下移">↓</button>
        </span>
      </div>
      <h3 class="q-title"></h3>
      <div class="vote-bars"></div>
      <div class="preview"></div>
      <div class="q-actions">
        <button class="btn btn--small act-activate">切換到此題</button>
        <button class="btn btn--small btn--primary-outline act-reset">清除數據</button>
        <button class="btn btn--small btn--ghost act-edit">編輯</button>
        <button class="btn btn--small btn--danger act-delete">刪除</button>
      </div>`;
    card.querySelector("h3").textContent = q.title;
    card.querySelector(".q-num").textContent = `第 ${index + 1} 題`;
    card.querySelector(".badge.type").textContent =
      q.type === "text" ? `文字 × ${q.options.length}` : "四格圖片";

    const up = card.querySelector(".act-up");
    const down = card.querySelector(".act-down");
    up.disabled = index === 0;
    down.disabled = index === questions.length - 1;
    up.addEventListener("click", () => moveQuestion(q.id, -1));
    down.addEventListener("click", () => moveQuestion(q.id, 1));

    card.querySelector(".act-activate").addEventListener("click", async () => {
      await api(`/api/questions/${q.id}/activate`, { method: "POST" });
    });
    card.querySelector(".act-reset").addEventListener("click", async () => {
      if (confirm(`確定清除「${q.title}」的所有投票數據，讓觀眾重新投票？`)) {
        await api(`/api/questions/${q.id}/reset`, { method: "POST" });
      }
    });
    card.querySelector(".act-edit").addEventListener("click", () => openModal(q));
    card.querySelector(".act-delete").addEventListener("click", async () => {
      if (confirm(`確定刪除題目「${q.title}」？`)) {
        await api(`/api/questions/${q.id}`, { method: "DELETE" });
      }
    });

    updateCard(card, q);
    return card;
  }

  function updateCard(card, q) {
    const isActive = q.id === activeId;
    card.classList.toggle("active", isActive);
    card.querySelector(".badge.live").hidden = !isActive;
    const actBtn = card.querySelector(".act-activate");
    actBtn.disabled = isActive;
    actBtn.textContent = isActive ? "✓ 進行中" : "▶ 切換到此題";

    const votes = q.votes || {};
    const total = Object.values(votes).reduce((a, b) => a + b, 0);
    const bars = card.querySelector(".vote-bars");
    if (bars.dataset.qkey !== q.id) {
      bars.dataset.qkey = q.id;
      bars.innerHTML = q.options.map((o) => `
        <div class="vote-bar" data-oid="${o.id}">
          <div class="bar-label"><span class="l"></span><span class="n"></span></div>
          <div class="bar-track"><div class="bar-fill" style="width:0%"></div></div>
        </div>`).join("");
      q.options.forEach((o, i) => {
        bars.querySelector(`[data-oid="${o.id}"] .l`).textContent =
          o.label || (q.type === "image4" ? `圖 ${i + 1}` : "");
      });
    }
    for (const o of q.options) {
      const row = bars.querySelector(`[data-oid="${o.id}"]`);
      if (!row) continue;
      const n = votes[o.id] || 0;
      row.querySelector(".n").textContent = `${n} 票`;
      row.querySelector(".bar-fill").style.width = total ? `${(n / total) * 100}%` : "0%";
    }

    const preview = card.querySelector(".preview");
    if (q.type === "text") {
      renderWordCloud(preview, q, { minPx: 12, maxPx: 30 });
    } else {
      renderPinMap(preview, q, { interactive: false });
    }
  }

  function refreshCard(q) {
    const card = $("cards").querySelector(`.q-card[data-qid="${q.id}"]`);
    if (card) updateCard(card, q);
  }

  // ---------- 新增 / 編輯表單 ----------

  function optionRow(type, opt = {}) {
    const row = document.createElement("div");
    row.className = "option-row";
    row.dataset.oid = opt.id || "";
    row.dataset.imageUrl = opt.image_url || "";
    if (type === "text") {
      row.innerHTML = `
        <input type="text" class="opt-label" placeholder="選項文字">
        <button type="button" class="btn btn--small btn--danger opt-remove">✕</button>`;
      row.querySelector(".opt-remove").addEventListener("click", () => {
        if ($("f-options").children.length > 2) row.remove();
      });
    } else {
      row.innerHTML = `
        <img class="thumb" alt="">
        <input type="text" class="opt-label" placeholder="圖片說明（選填）">
        <input type="file" class="opt-file" accept="image/png,image/jpeg,image/webp,image/svg+xml">`;
      const thumb = row.querySelector(".thumb");
      thumb.src = row.dataset.imageUrl;
      thumb.style.cursor = "zoom-in";
      thumb.addEventListener("click", () => {
        if (row.dataset.imageUrl) {
          openLightbox(row.dataset.imageUrl, row.querySelector(".opt-label").value);
        }
      });
      row.querySelector(".opt-file").addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        try {
          const res = await fetch("/api/upload", {
            method: "POST",
            headers: { "X-Admin-Token": adminToken() },
            body: fd,
          });
          if (!res.ok) throw new Error((await res.json()).detail || "上傳失敗");
          const { url } = await res.json();
          row.dataset.imageUrl = url;
          row.querySelector(".thumb").src = url;
        } catch (err) {
          $("f-error").textContent = err.message;
        }
      });
    }
    row.querySelector(".opt-label").value = opt.label || "";
    return row;
  }

  function fillOptionRows(type, options) {
    const box = $("f-options");
    box.innerHTML = "";
    if (type === "image4") {
      const opts = options && options.length === 4 ? options
        : DEFAULT_IMAGES.map((u) => ({ label: "", image_url: u }));
      opts.forEach((o) => box.appendChild(optionRow("image4", o)));
    } else {
      const opts = options && options.length >= 2 ? options : [{}, {}];
      opts.forEach((o) => box.appendChild(optionRow("text", o)));
    }
    $("btn-add-option").hidden = type === "image4";
  }

  function openModal(q = null) {
    editingId = q ? q.id : null;
    $("modal-title").textContent = q ? "編輯題目" : "新增題目";
    $("f-title").value = q ? q.title : "";
    $("f-type").value = q ? q.type : "text";
    $("f-type").disabled = !!q; // 編輯時不允許改題型（票數/針位語意不同）
    $("f-error").textContent = "";
    fillOptionRows($("f-type").value, q ? q.options : null);
    $("modal-backdrop").hidden = false;
  }

  async function saveModal() {
    const type = $("f-type").value;
    const options = [...$("f-options").children].map((row) => {
      const o = { label: row.querySelector(".opt-label").value.trim() };
      if (row.dataset.oid) o.id = row.dataset.oid;
      if (type === "image4") o.image_url = row.dataset.imageUrl;
      return o;
    });
    const payload = { title: $("f-title").value, type, options };
    try {
      if (editingId) {
        await api(`/api/questions/${editingId}`, { method: "PUT", body: JSON.stringify(payload) });
      } else {
        await api("/api/questions", { method: "POST", body: JSON.stringify(payload) });
      }
      $("modal-backdrop").hidden = true;
    } catch (err) {
      $("f-error").textContent = err.message;
    }
  }

  $("btn-new").addEventListener("click", () => openModal());
  $("btn-cancel").addEventListener("click", () => { $("modal-backdrop").hidden = true; });
  $("btn-save").addEventListener("click", saveModal);
  $("f-type").addEventListener("change", () => fillOptionRows($("f-type").value, null));
  $("btn-add-option").addEventListener("click", () => {
    $("f-options").appendChild(optionRow("text"));
  });

  // ---------- QR Code ----------

  const voteUrl = `${location.origin}/`;
  $("qr-url").textContent = voteUrl;
  $("qr-img").src = `/api/qrcode?text=${encodeURIComponent(voteUrl)}`;
  // 點 QR Code 可放大（後台與投影頁）
  for (const id of ["qr-img", "p-qr"]) {
    const img = $(id);
    img.style.cursor = "zoom-in";
    img.addEventListener("click", () => openLightbox(img.src, "掃描加入投票", { stretch: true }));
  }

  // ---------- 全螢幕投影（結果顯示） ----------

  const projEl = $("projection");

  const cloudSizes = () => ({
    minPx: Math.max(26, Math.round(window.innerHeight * 0.035)),
    maxPx: Math.max(64, Math.round(window.innerHeight * 0.13)),
  });

  function renderProjection() {
    if (projEl.hidden) return;
    const idx = questions.findIndex((x) => x.id === activeId);
    const q = idx >= 0 ? questions[idx] : null;
    $("p-waiting").hidden = !!q;
    $("p-title").hidden = !q;
    $("p-prev").disabled = idx <= 0;
    $("p-next").disabled = idx === -1 ? !questions.length : idx >= questions.length - 1;
    $("p-reset").disabled = !q;
    if (!q) {
      $("p-num").textContent = "";
      $("p-total").textContent = "";
      $("p-cloud").hidden = true;
      $("p-map").hidden = true;
      return;
    }
    $("p-num").textContent = `第 ${idx + 1} 題 / 共 ${questions.length} 題`;
    $("p-title").textContent = q.title;
    const total = Object.values(q.votes || {}).reduce((a, b) => a + b, 0);
    $("p-total").textContent = `已收到 ${total} 票`;
    if (q.type === "text") {
      $("p-map").hidden = true;
      $("p-cloud").hidden = false;
      renderWordCloud($("p-cloud"), q, cloudSizes());
    } else {
      $("p-cloud").hidden = true;
      $("p-map").hidden = false;
      renderPinMap($("p-map"), q, { interactive: false });
    }
  }

  function openProjection() {
    projEl.hidden = false;
    renderProjection();
    if (projEl.requestFullscreen) projEl.requestFullscreen().catch(() => {});
  }

  function closeProjection() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    projEl.hidden = true;
  }

  async function stepQuestion(delta) {
    const idx = questions.findIndex((x) => x.id === activeId);
    const target = idx === -1 ? (delta > 0 ? questions[0] : null) : questions[idx + delta];
    if (target) await api(`/api/questions/${target.id}/activate`, { method: "POST" });
  }

  $("btn-project").addEventListener("click", openProjection);
  $("p-exit").addEventListener("click", closeProjection);
  $("p-prev").addEventListener("click", () => stepQuestion(-1));
  $("p-next").addEventListener("click", () => stepQuestion(1));
  $("p-reset").addEventListener("click", async () => {
    const q = questions.find((x) => x.id === activeId);
    if (q && confirm(`確定清除「${q.title}」的所有投票數據，讓觀眾重新投票？`)) {
      await api(`/api/questions/${q.id}/reset`, { method: "POST" });
    }
  });
  document.addEventListener("fullscreenchange", () => {
    // 按 ESC 或瀏覽器退出全螢幕時，一併關閉覆蓋層
    if (!document.fullscreenElement) projEl.hidden = true;
  });
  window.addEventListener("resize", renderProjection);

  $("p-url").textContent = voteUrl.replace(/^https?:\/\//, "");
  $("p-qr").src = `/api/qrcode?text=${encodeURIComponent(voteUrl)}`;

  // ---------- WebSocket 即時同步 ----------

  const client = new WSClient("/ws?role=admin")   // admin 角色才會收到即時票數推送
    .on("_open", () => {
      const el = $("conn-status");
      el.textContent = "● 即時連線中";
      el.classList.remove("off");
    })
    .on("_close", () => {
      const el = $("conn-status");
      el.textContent = "● 連線中斷，重試中……";
      el.classList.add("off");
    })
    .on("state:init", () => loadQuestions())     // 首次與重連後全量對齊
    .on("questions:changed", () => loadQuestions())
    .on("question:switch", (p) => {
      activeId = p.question ? p.question.id : null;
      questions.forEach((q) => refreshCard(q));
      renderProjection();
    })
    .on("vote:update", (p) => {
      const q = questions.find((x) => x.id === p.questionId);
      if (!q || p.round !== q.round) return;
      q.votes = p.votes;
      (p.newPins || []).forEach((pin) => q.pins.push(pin));
      if (p.removedPinIds && p.removedPinIds.length) {
        q.pins = q.pins.filter((pin) => !p.removedPinIds.includes(pin.id));
      }
      refreshCard(q);
      if (q.id === activeId) renderProjection();
    })
    .on("vote:reset", (p) => {
      const i = questions.findIndex((x) => x.id === p.questionId);
      if (i === -1) return;
      questions[i] = p.question;
      refreshCard(questions[i]);
      renderProjection();
    })
    .connect();
})();
