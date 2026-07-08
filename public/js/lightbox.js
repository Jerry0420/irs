/* 圖片燈箱：點圖放大顯示，點任意處或按 ESC 關閉
   opts.stretch: 強制撐大（QR Code 等原始尺寸很小的向量圖用） */
function openLightbox(src, caption = "", opts = {}) {
  let box = document.getElementById("lightbox");
  if (!box) {
    box = document.createElement("div");
    box.id = "lightbox";
    box.className = "lightbox";
    box.innerHTML = '<div class="lightbox-frame"><img alt="">' +
      '<button type="button" class="lightbox-close" aria-label="關閉">✕</button></div>' +
      '<div class="lightbox-caption"></div>';
    box.addEventListener("click", () => { box.hidden = true; });  // 點任意處關閉（保留）
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") box.hidden = true;
    });
    document.body.appendChild(box);
  }
  // 全螢幕模式只會渲染全螢幕元素的內部，燈箱必須掛進去才看得到
  (document.fullscreenElement || document.body).appendChild(box);
  const img = box.querySelector("img");
  img.src = src;
  img.style.width = opts.stretch ? "min(60vw, 52vh)" : "";
  box.querySelector(".lightbox-caption").textContent = caption;
  box.hidden = false;
}
