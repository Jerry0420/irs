/* 文字雲：字級隨「絕對票數」沿飽和曲線持續放大（每一票都變大、逐漸逼近上限），
   並依容器寬度與字數鉗制，避免超出螢幕。縮放動畫由 CSS transition 承擔。 */
function renderWordCloud(container, question, opts = {}) {
  const minPx = opts.minPx || 14;
  const maxPx = opts.maxPx || 64;  // 尺度校準值（150 票時達此字級），不是上限
  const showCount = opts.showCount !== false;

  if (container.dataset.qkey !== question.id) {
    container.dataset.qkey = question.id;
    container.innerHTML = "";
    container.classList.add("wordcloud");
    for (const o of question.options) {
      const el = document.createElement("span");
      el.className = "word";
      el.dataset.oid = o.id;
      el.innerHTML = `<span class="label"></span>${showCount ? '<span class="count"></span>' : ""}`;
      el.querySelector(".label").textContent = o.label;
      container.appendChild(el);
    }
    // 隱藏量測元素：以 100px 基準實測標籤渲染寬度，供字級上限精準換算
    const meter = document.createElement("span");
    meter.className = "word word-meter";
    meter.setAttribute("aria-hidden", "true");
    meter.innerHTML = '<span class="label"></span><span class="count"></span>';
    container.appendChild(meter);
  }
  const meter = container.querySelector(":scope > .word-meter");

  const votes = question.votes || {};
  const containerWidth = container.clientWidth || 320;
  const totalVotes = Object.values(votes).reduce((a, b) => a + b, 0);
  const maxVotes = Math.max(0, ...question.options.map((o) => votes[o.id] || 0));
  // 整體上限以平方根曲線隨總票數持續成長，到 fullVotes 才到頂：
  // 前期每票放大明顯，中後期仍持續有感，不會提早飽和「卡住」。
  // 各選項以「相對領先者的比例」的 CONTRAST 次方決定字級——
  // 指數夠大時，領先者每得一票，落後者的比例下降會壓過整體上限的成長，
  // 視覺上「一個放大、其他同步縮小」，維持與票數相稱的大小比例。
  // KNEE 只是曲線轉折點，不是上限：之前用 0.75 次方曲線（前期每票放大明顯），
  // 之後轉為「線性」——每票固定 +range/KNEE px，成長速度永不衰減、無封頂；
  // 爆版由下方的「標籤寬度鉗制」把關。
  const KNEE = 150;
  const range = maxPx - minPx;
  const effectiveMax = totalVotes <= KNEE
    ? minPx + range * Math.pow(totalVotes / KNEE, 0.75)
    : maxPx + range * (totalVotes - KNEE) / KNEE;
  // 對比指數隨總票數 1 → 2.5 遞增：開場各選項大小接近，
  // 票越多、比例的放大倍率越強，即使票數比固定，大小差距也持續拉開。
  const contrast = 1 + Math.min(1.5, 0.2 * Math.log2(1 + totalVotes));
  for (const o of question.options) {
    const el = container.querySelector(`.word[data-oid="${o.id}"]`);
    if (!el) continue;
    const n = votes[o.id] || 0;
    const ratio = maxVotes > 0 ? Math.pow(n / maxVotes, contrast) : 0;
    let px = minPx + (effectiveMax - minPx) * ratio;
    // 碰到外框就停止放大：實測 100px 字級下的渲染寬度，等比換算「剛好貼到容器」的字級上限
    if (meter) {
      meter.querySelector(".label").textContent = o.label;
      meter.querySelector(".count").textContent = showCount && n > 0 ? String(n) : "";
      const w100 = meter.offsetWidth || 1;
      px = Math.min(px, (containerWidth * 0.92) * 100 / w100);
    }
    px = Math.min(px, window.innerHeight * 0.35);  // 直向也不得超出畫面
    el.style.fontSize = `${Math.round(px * 10) / 10}px`;
    el.style.color = n > 0 ? "var(--ink)" : "var(--ink-soft)";
    if (showCount) el.querySelector(".count").textContent = n > 0 ? String(n) : "";
  }
}
