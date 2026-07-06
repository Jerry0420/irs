/* 觀眾投票頁：即時同步題目、投票、每題一票鎖定、取消重投、結果動態呈現 */
(() => {
  const $ = (id) => document.getElementById(id);
  const els = {
    banner: $("lock-banner"),
    cancelBtn: $("btn-cancel-vote"),
    number: $("q-number"),
    title: $("q-title"),
    options: $("options"),
    cloud: $("cloud"),
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

  let current = null;      // 目前題目（含 votes / pins / round）
  let sending = false;     // 防連點：等待伺服器回覆期間鎖住

  const votedKey = (q) => `irs-voted:${q.id}:${q.round}`;
  const hasVoted = (q) => !!localStorage.getItem(votedKey(q));

  function render() {
    const q = current;
    els.waiting.hidden = !!q;
    els.title.hidden = !q;
    els.number.hidden = !q || !q.number;
    if (!q) {
      els.banner.hidden = true;
      els.options.hidden = true;
      els.cloud.hidden = true;
      els.map.hidden = true;
      return;
    }

    if (q.number) els.number.textContent = `第 ${q.number} 題`;
    els.title.textContent = q.title;
    const voted = hasVoted(q);
    els.banner.hidden = !voted;
    els.cancelBtn.disabled = sending;

    if (q.type === "text") {
      els.map.hidden = true;
      els.options.hidden = voted;
      els.cloud.hidden = !voted;
      if (voted) {
        renderWordCloud(els.cloud, q);
      } else {
        renderTextOptions(q);
      }
    } else {
      els.options.hidden = true;
      els.cloud.hidden = true;
      els.map.hidden = false;
      renderPinMap(els.map, q, {
        interactive: !voted,
        onPick: (optionId, pin) => castVote(q, optionId, pin),
      });
    }
  }

  function renderTextOptions(q) {
    if (els.options.dataset.qkey !== `${q.id}:${q.round}`) {
      els.options.dataset.qkey = `${q.id}:${q.round}`;
      els.options.innerHTML = "";
      for (const o of q.options) {
        const btn = document.createElement("button");
        btn.className = "btn";
        btn.textContent = o.label;
        btn.addEventListener("click", () => castVote(q, o.id, null));
        els.options.appendChild(btn);
      }
    }
    els.options.querySelectorAll("button").forEach((b) => (b.disabled = sending));
  }

  function castVote(q, optionId, pin) {
    if (sending || hasVoted(q)) return;
    sending = true;
    render();
    const ok = client.send("vote:cast", { questionId: q.id, optionId, pin, voterId });
    if (!ok) { sending = false; render(); }
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
        localStorage.setItem(votedKey(current), "1");
      }
      render();
    })
    .on("vote:rejected", (p) => {
      sending = false;
      if (current && p.reason === "already_voted") {
        localStorage.setItem(votedKey(current), "1");
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
    .on("vote:update", (p) => {
      if (!current || p.questionId !== current.id || p.round !== current.round) return;
      current.votes = p.votes;
      (p.newPins || []).forEach((pin) => current.pins.push(pin));
      if (p.removedPinIds && p.removedPinIds.length) {
        current.pins = current.pins.filter((pin) => !p.removedPinIds.includes(pin.id));
      }
      render();
    })
    .on("vote:reset", (p) => {
      if (!current || p.questionId !== current.id) return;
      current = p.question;   // 新 round：votes/pins 已清空，localStorage 鍵值換新即自動解鎖
      sending = false;
      render();
    })
    .connect();
})();
