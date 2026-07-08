/* 觀眾投票頁：即時同步題目、投票、每題一票鎖定、取消重投。
   不接收即時結果（文字雲/圖釘由後台與投影頁呈現），只顯示自己的投票回饋。 */
(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    banner: $("lock-banner"),
    cancelBtn: $("btn-cancel-vote"),
    choice: $("my-choice"),
    number: $("q-number"),
    title: $("q-title"),
    options: $("options"),
    map: $("map"),
    waiting: $("waiting"),
  };

  // 觀眾匿名識別碼：伺服器以此記錄每題一票，並支援「取消投票」（重新整理後仍有效）
  let voterId = localStorage.getItem("irs-voter-id");
  if (!voterId) {
    voterId = (crypto.randomUUID && crypto.randomUUID()) ||
      `${Date.now().toString(16)}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem("irs-voter-id", voterId);
  }

  let current = null;       // 目前題目（觀眾版 payload，不含票數/圖釘）
  let sending = false;      // 防連點：等待伺服器回覆期間鎖住
  let pendingCast = null;   // 送出中的投票內容（等 vote:accepted 後存起來）

  const votedKey = (q) => `irs-voted:${q.id}:${q.round}`;

  function votedRecord(q) {
    const raw = localStorage.getItem(votedKey(q));
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return {}; }  // 舊格式相容
  }

  function optionLabel(q, optionId) {
    const i = q.options.findIndex((o) => o.id === optionId);
    if (i === -1) return "";
    return q.options[i].label || `圖 ${i + 1}`;
  }

  function render() {
    const q = current;
    els.waiting.hidden = !!q;
    els.title.hidden = !q;
    els.number.hidden = !q || !q.number;
    if (!q) {
      els.banner.hidden = true;
      els.options.hidden = true;
      els.map.hidden = true;
      return;
    }

    if (q.number) els.number.textContent = `第 ${q.number} 題`;
    els.title.textContent = q.title;

    const record = votedRecord(q);
    els.banner.hidden = !record;
    els.cancelBtn.disabled = sending;
    const label = record ? optionLabel(q, record.optionId) : "";
    els.choice.hidden = !label;
    if (label) els.choice.textContent = `您投給了「${label}」`;

    if (q.type === "text") {
      els.map.hidden = true;
      els.options.hidden = false;   // 投完票選項仍顯示：鎖定 + 高亮自己的選擇
      renderTextOptions(q, record);
    } else {
      els.options.hidden = true;
      els.map.hidden = false;
      // 只顯示自己的大頭針，不顯示其他觀眾的結果
      const ownPins = record && record.pin
        ? [{ id: "own", option_id: record.optionId, x: record.pin.x, y: record.pin.y }]
        : [];
      renderPinMap(els.map, { ...q, pins: ownPins }, {
        interactive: !record,
        onPick: (optionId, pin) => castVote(q, optionId, pin),
      });
    }
  }

  function renderTextOptions(q, record) {
    if (els.options.dataset.qkey !== `${q.id}:${q.round}`) {
      els.options.dataset.qkey = `${q.id}:${q.round}`;
      els.options.innerHTML = "";
      for (const o of q.options) {
        const btn = document.createElement("button");
        btn.className = "btn";
        btn.dataset.oid = o.id;
        btn.textContent = o.label;
        btn.addEventListener("click", () => castVote(q, o.id, null));
        els.options.appendChild(btn);
      }
    }
    els.options.querySelectorAll("button").forEach((b) => {
      b.disabled = sending || !!record;
      b.classList.toggle("chosen", !!record && record.optionId === b.dataset.oid);
    });
  }

  function castVote(q, optionId, pin) {
    if (sending || votedRecord(q)) return;
    sending = true;
    pendingCast = { optionId, pin };
    render();
    const ok = client.send("vote:cast", { questionId: q.id, optionId, pin, voterId });
    if (!ok) { sending = false; pendingCast = null; render(); }
  }

  function cancelVote() {
    if (sending || !current) return;
    sending = true;
    render();
    const ok = client.send("vote:cancel", { questionId: current.id, voterId });
    if (!ok) { sending = false; render(); }
  }

  els.cancelBtn.addEventListener("click", cancelVote);

  const client = new WSClient()
    .on("state:init", (p) => {
      current = p.question;
      sending = false;
      render();
    })
    .on("question:switch", (p) => {
      current = p.question;
      sending = false;
      render();
    })
    .on("vote:accepted", (p) => {
      sending = false;
      if (current && p.questionId === current.id) {
        localStorage.setItem(votedKey(current), JSON.stringify(pendingCast || {}));
      }
      pendingCast = null;
      render();
    })
    .on("vote:rejected", (p) => {
      sending = false;
      pendingCast = null;
      if (current && p.reason === "already_voted") {
        localStorage.setItem(votedKey(current), JSON.stringify({}));
      }
      render();
    })
    .on("vote:cancelled", (p) => {
      sending = false;
      if (current && p.questionId === current.id) {
        localStorage.removeItem(votedKey(current));
      }
      render();
    })
    .on("cancel:rejected", (p) => {
      sending = false;
      // 伺服器已無此投票紀錄（例如已被清除數據）→ 同步解除本機鎖定
      if (current && p.reason === "not_voted") {
        localStorage.removeItem(votedKey(current));
      }
      render();
    })
    .on("vote:reset", (p) => {
      if (!current || p.questionId !== current.id) return;
      current = p.question;   // 新 round：localStorage 鍵值換新即自動解鎖
      sending = false;
      render();
    })
    .connect();
})();
