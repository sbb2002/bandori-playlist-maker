// ── Camelot Wheel 궤적 시각화 ─────────────────────────────────────────────
let wheelLabelMode = "camelot"; // "camelot" | "key"
let wheelRingLabelEls = null;
let wheelNodeEls = [];
let wheelEdgeEls = []; // { el, from, to } — 거리 기반 투명도 계산용
let wheelTrackCount = 0;
const WHEEL_MIN_OPACITY = 0.1;
const WHEEL_CX = 210, WHEEL_CY = 210;
const WHEEL_R_OUTER = 170, WHEEL_R_INNER = 118;
const WHEEL_R_MAJOR_DOT = (WHEEL_R_OUTER + WHEEL_R_INNER) / 2 + 20;
const WHEEL_R_MINOR_DOT = WHEEL_R_INNER - 20;

function svgEl(tag, attrs) {
  const e = document.createElementNS(SVG_NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
function wheelAngle(num) { return (num / 12) * 2 * Math.PI - Math.PI / 2; }
function wheelPoint(radius, num) {
  const a = wheelAngle(num);
  return [WHEEL_CX + radius * Math.cos(a), WHEEL_CY + radius * Math.sin(a)];
}
function wheelRadiusFor(letter) { return letter === "B" ? WHEEL_R_MAJOR_DOT : WHEEL_R_MINOR_DOT; }

function renderCamelotWheel(list) {
  wheelSvgEl.replaceChildren();
  if (!list.length) return;

  wheelSvgEl.appendChild(svgEl("circle", { cx: WHEEL_CX, cy: WHEEL_CY, r: WHEEL_R_OUTER, class: "ring-major" }));
  wheelSvgEl.appendChild(svgEl("circle", { cx: WHEEL_CX, cy: WHEEL_CY, r: WHEEL_R_INNER, class: "ring-minor" }));
  wheelSvgEl.appendChild(svgEl("circle", { cx: WHEEL_CX, cy: WHEEL_CY, r: WHEEL_R_INNER - 40, class: "ring-minor" }));

  const majorLabelEls = {};
  const minorLabelEls = {};
  for (let n = 1; n <= 12; n++) {
    const [mx, my] = wheelPoint(WHEEL_R_MAJOR_DOT, n);
    const [ix, iy] = wheelPoint(WHEEL_R_MINOR_DOT, n);
    wheelSvgEl.appendChild(svgEl("circle", { cx: mx, cy: my, r: 15, class: "slot-major" }));
    wheelSvgEl.appendChild(svgEl("circle", { cx: ix, cy: iy, r: 13, class: "slot-minor" }));
    const lm = svgEl("text", { x: mx, y: my, class: "ring-label", "text-anchor": "middle", "dominant-baseline": "central" });
    wheelSvgEl.appendChild(lm);
    majorLabelEls[n] = lm;
    const li = svgEl("text", { x: ix, y: iy, class: "ring-label", "text-anchor": "middle", "dominant-baseline": "central" });
    wheelSvgEl.appendChild(li);
    minorLabelEls[n] = li;
  }
  wheelRingLabelEls = { major: majorLabelEls, minor: minorLabelEls };
  updateWheelRingLabels();

  const pathPts = list.map((p) => {
    const c = p.camelot || "";
    const letter = c.slice(-1);
    const num = parseInt(c, 10);
    return isFinite(num) ? wheelPoint(wheelRadiusFor(letter), num) : null;
  });

  wheelEdgeEls = [];
  wheelTrackCount = list.length;
  for (let i = 1; i < list.length; i++) {
    if (!pathPts[i - 1] || !pathPts[i]) continue;
    const [x1, y1] = pathPts[i - 1];
    const [x2, y2] = pathPts[i];
    const h = list[i].reason ? list[i].reason.harmonic : "";
    const cls = (h === "same" || h === "adjacent") ? "ok-edge" : "warn-edge";
    const d = `M${x1.toFixed(1)},${y1.toFixed(1)} L${x2.toFixed(1)},${y2.toFixed(1)}`;
    const seg = svgEl("path", { d, class: "path-line " + cls });
    wheelSvgEl.appendChild(seg);
    wheelEdgeEls.push({ el: seg, from: i - 1, to: i });
  }
  updateWheelEdgeOpacity(current);

  wheelNodeEls = [];
  list.forEach((p, i) => {
    if (!pathPts[i]) return;
    const [x, y] = pathPts[i];
    const g = svgEl("g", { class: "wnode" });
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 13, class: "whalo" }));
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 9, class: "wdot" }));
    const t = svgEl("text", { x, y, class: "wn" });
    t.textContent = i + 1;
    g.appendChild(t);
    g.addEventListener("click", () => playSong(i, false));
    wheelSvgEl.appendChild(g);
    wheelNodeEls.push(g);
  });
}

function updateWheelRingLabels() {
  if (!wheelRingLabelEls) return;
  for (let n = 1; n <= 12; n++) {
    const bCode = n + "B", aCode = n + "A";
    wheelRingLabelEls.major[n].textContent = wheelLabelMode === "camelot" ? bCode : keyLabel(bCode);
    wheelRingLabelEls.minor[n].textContent = wheelLabelMode === "camelot" ? aCode : keyLabel(aCode);
  }
}

// 현재 재생 곡에서 멀어질수록(트랙 순서 기준) 선을 점점 투명하게 — 최소 WHEEL_MIN_OPACITY까지.
function updateWheelEdgeOpacity(currentIdx) {
  if (currentIdx == null || currentIdx < 0) currentIdx = 0;
  const maxDist = Math.max(1, wheelTrackCount - 1);
  wheelEdgeEls.forEach(({ el, from, to }) => {
    const dist = Math.min(Math.abs(from - currentIdx), Math.abs(to - currentIdx));
    const t = Math.min(1, dist / maxDist);
    el.style.opacity = (1 - t * (1 - WHEEL_MIN_OPACITY)).toFixed(3);
  });
}

wheelModeToggleEl.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-mode]");
  if (!btn) return;
  wheelLabelMode = btn.dataset.mode;
  wheelModeToggleEl.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
  updateWheelRingLabels();
});

