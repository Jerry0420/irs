/* 圖片燈箱：點圖放大顯示，點任意處或按 ESC 關閉 */
function openLightbox(src, caption = "") {
  let box = document.getElementById("lightbox");
  if (!box) {
    box = document.createElement("div");
    box.id = "lightbox";
    box.className = "lightbox";
    box.innerHTML = '<img alt=""><div class="lightbox-caption"></div>';
    box.addEventListener("click", () => { box.hidden = true; });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") box.hidden = true;
    });
    document.body.appendChild(box);
  }
  box.querySelector("img").src = src;
  box.querySelector(".lightbox-caption").textContent = caption;
  box.hidden = false;
}
