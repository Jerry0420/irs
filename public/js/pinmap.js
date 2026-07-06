/* 2×2 圖片插針：2×2 圖格 + 相對座標 (0~1) 大頭針疊層，新針帶落下動畫 */
function renderPinMap(container, question, opts = {}) {
  const interactive = !!opts.interactive;

  container.classList.add("pinmap");
  container.classList.toggle("interactive", interactive);

  if (container.dataset.qkey !== `${question.id}:${question.round}`) {
    container.dataset.qkey = `${question.id}:${question.round}`;
    container.innerHTML = "";
    for (const o of question.options) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.dataset.oid = o.id;
      const img = document.createElement("img");
      img.src = o.image_url;
      img.alt = o.label;
      cell.appendChild(img);
      if (o.label) {  // 沒填說明就不壓黑條文字
        const label = document.createElement("div");
        label.className = "cell-label";
        label.textContent = o.label;
        cell.appendChild(label);
      }
      if (typeof openLightbox === "function") {
        // 🔍 放大鈕：不影響投票點擊
        const zoom = document.createElement("button");
        zoom.type = "button";
        zoom.className = "cell-zoom";
        zoom.title = "放大圖片";
        zoom.textContent = "🔍";
        zoom.addEventListener("click", (e) => {
          e.stopPropagation();
          openLightbox(o.image_url, o.label);
        });
        cell.appendChild(zoom);
      }
      cell.addEventListener("click", (e) => {
        if (container.classList.contains("interactive")) {
          if (!opts.onPick) return;   // 投票模式：點圖 = 投票
          const rect = cell.getBoundingClientRect();
          const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
          const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
          opts.onPick(o.id, { x, y });
        } else if (typeof openLightbox === "function") {
          openLightbox(o.image_url, o.label);  // 非投票模式：點圖 = 放大
        }
      });
      container.appendChild(cell);
    }
  }

  // 以 pin id 做差異渲染：新針播放落下動畫、被取消的針淡出移除
  const pins = question.pins || [];
  const wanted = new Set(pins.map((p) => p.id));
  container.querySelectorAll(".pin:not(.pin-out)").forEach((el) => {
    if (!wanted.has(el.dataset.pid)) {
      el.classList.add("pin-out");
      setTimeout(() => el.remove(), 450);
    }
  });
  for (const pin of pins) {
    if (container.querySelector(`.pin[data-pid="${pin.id}"]:not(.pin-out)`)) continue;
    const cell = container.querySelector(`.cell[data-oid="${pin.option_id}"]`);
    if (!cell) continue;
    const dot = document.createElement("div");
    dot.className = "pin";
    dot.dataset.pid = pin.id;
    dot.style.left = `${pin.x * 100}%`;
    dot.style.top = `${pin.y * 100}%`;
    cell.appendChild(dot);
  }
}
