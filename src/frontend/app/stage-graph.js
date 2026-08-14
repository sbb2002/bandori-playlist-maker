// 2D 정서 지도 + 시간 배분 + 고급 설정 편집기 (§5-1a)
// SVG_NS/clamp01은 app/utils.js 참조.
const MAP_PAD = 8; // 지도 여백(%)
const toMapPct = (frac) => MAP_PAD + frac * (100 - MAP_PAD * 2);
const fromMapPct = (pct) => clamp01((pct - MAP_PAD) / (100 - MAP_PAD * 2));
const MIN_SEGMENTS = 2;  // 구간 최소 개수
const MAX_SEGMENTS = 11; // 구간 최대 개수
const DEFAULT_STAGE_COUNT = 3; // 기본 구간 수
const MIN_WIDTH_MIN = 3; // 구간 최소 길이(분) — 구간이 너무 촘촘해지면 곡 배정이 어색해짐

// 고급 설정 그래프 5개 — label/desc는 함수로 두어 언어 전환 후 재빌드 시 최신 번역을 읽는다.
const PARAM_DEFS = [
  { key: "lufs_integrated", get label() { return t("param.lufs.label"); }, get desc() { return t("param.lufs.desc"); } },
  { key: "lra", get label() { return t("param.lra.label"); }, get desc() { return t("param.lra.desc"); } },
  { key: "danceability_norm", get label() { return t("param.dance.label"); }, get desc() { return t("param.dance.desc"); } },
  { key: "instr_stem_ratio", get label() { return t("param.instr.label"); }, get desc() { return t("param.instr.desc"); } },
  { key: "speech_median", get label() { return t("param.speech.label"); }, get desc() { return t("param.speech.desc"); } },
];

// 고급 설정 그래프용 여백
const PAD_TOP = 10;      // 그래프 상하 여백(뷰박스 0~100 기준)
const PAD_BOTTOM = 6;
const valToY = (v) => PAD_TOP + (1 - v) * (100 - PAD_TOP - PAD_BOTTOM);
const yToVal = (fracY) => clamp01(1 - (fracY * 100 - PAD_TOP) / (100 - PAD_TOP - PAD_BOTTOM));

// stageModel: { totalMinutes, segments: [{energy, width, valence, lufs_integrated, lra, danceability_norm, instr_stem_ratio, speech_median}] }
let stageModel = null;

// GET /api/feature-stats 결과(캐시) — 없으면(로딩 전/실패) 희소 힌트는 그냥 안 그림.
let featureStats = null;

// 백엔드도 180분(3시간) 하드캡을 두지만(routes.py _MAX_TARGET_MINUTES), 여기서도 넘긴 순간
// 180으로 되돌리고 안내한다(number input의 native max는 스핀 버튼만 막고 타이핑은 안 막음).
minutesEl.addEventListener("input", () => {
  minutesTouched = true;
  const n = parseInt(minutesEl.value, 10);
  if (!Number.isNaN(n) && n > 180) {
    minutesEl.value = 180;
    minutesHintEl.textContent = t("options.minutesMax");
    minutesHintEl.classList.add("notice");
  } else {
    minutesHintEl.textContent = "";
    minutesHintEl.classList.remove("notice");
  }
  if (stageModel) {
    stageModel.totalMinutes = clampInt(minutesEl.value, 10, 180, 60);
    renderStageGraph();
  }
});
// 곡 종류(ALL/Original/Cover) — 셋 중 항상 하나만 켜지는 토글 버튼. ALL이 꺼지는 유일한 경로는
// Original/Cover를 켤 때뿐이고, 그 반대(Original·Cover가 둘 다 꺼짐)는 항상 ALL로 귀결시킨다.
function typeToFlags(type) {
  if (type === "original") return { include_original: true, include_cover: false };
  if (type === "cover") return { include_original: false, include_cover: true };
  return { include_original: true, include_cover: true }; // all
}
function flagsToType(incOriginal, incCover) {
  if (incOriginal && !incCover) return "original";
  if (!incOriginal && incCover) return "cover";
  return "all"; // 둘 다 켜짐 = ALL, 둘 다 꺼짐(있어선 안 되는 상태)도 안전하게 ALL로 귀결
}
function renderSettingsTypeFilter() {
  const el = $("settings-type-filter");
  el.replaceChildren();
  for (const { key, label } of PICKER_TYPE_OPTIONS) {
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "picker-type-pill" + (settingsType === key ? " active" : "");
    pill.textContent = label;
    pill.addEventListener("click", () => {
      if (settingsType === key) return; // 켜진 버튼을 다시 누르면 무시 — 항상 하나는 켜져 있어야 함
      coverTouched = true;
      settingsType = key;
      renderSettingsTypeFilter();
    });
    el.appendChild(pill);
  }
}
renderSettingsTypeFilter();

// 2D 정서 지도 + 시간 배분 + 고급 설정 그래프들
function centers() {
  if (!stageModel) return { cum: [0], mid: [] };
  const cum = [0];
  stageModel.segments.forEach((s) => cum.push(cum[cum.length - 1] + s.width));
  return { cum, mid: stageModel.segments.map((s, i) => (cum[i] + cum[i + 1]) / 2) };
}

function smoothPath(pts) {
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6, c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6, c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
  }
  return d;
}

function initStageModel(n = DEFAULT_STAGE_COUNT) {
  const count = Math.max(MIN_SEGMENTS, Math.min(MAX_SEGMENTS, n));
  const total = clampInt($("target-minutes").value, 10, 180, 60);
  const segments = [];
  for (let i = 0; i < count; i++) {
    segments.push({
      width: 1 / count,
      valence: 0.5,
      energy: +(0.3 + (0.55 * i) / (count - 1)).toFixed(2),
      lufs_integrated: 0.5,
      lra: 0.5,
      danceability_norm: 0.5,
      instr_stem_ratio: 0.5,
      speech_median: 0.5,
      impression: "",
      bands: [],
    });
  }
  stageModel = { totalMinutes: total, segments };
}

function renderStageGraph() {
  if (!stageModel) initStageModel();

  function buildAllGraphics() {
    buildMap();
    buildTimebar();
    buildImpressionRow();
    buildParamGraphs();
    updateAllGraphics();
  }

  function updateAllGraphics() {
    updateMap();
    updateTimebar();
    updateImpressionRow();
    updateAllParamCharts();
    stageNEl.textContent = t("options.stageCount", { n: stageModel.segments.length });
    stageMinusBtn.disabled = stageModel.segments.length <= MIN_SEGMENTS;
    stagePlusBtn.disabled = stageModel.segments.length >= MAX_SEGMENTS;
  }

  // ── 2D 정서 지도 ──────────────────────────────────────────────────────────
  let mapNodeEls = [];

  function buildMap() {
    mapSvgEl.innerHTML = "";
    const gridG = document.createElementNS(SVG_NS, "g");
    [0, 25, 50, 75, 100].forEach((p) => {
      const v = document.createElementNS(SVG_NS, "line");
      v.setAttribute("x1", p); v.setAttribute("x2", p); v.setAttribute("y1", 0); v.setAttribute("y2", 100);
      v.setAttribute("class", "map-grid" + (p === 50 ? " mid" : ""));
      const h = document.createElementNS(SVG_NS, "line");
      h.setAttribute("y1", p); h.setAttribute("y2", p); h.setAttribute("x1", 0); h.setAttribute("x2", 100);
      h.setAttribute("class", "map-grid" + (p === 50 ? " mid" : ""));
      gridG.append(v, h);
    });
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("class", "map-path");
    path.setAttribute("id", "map-path-line");
    const defs = document.createElementNS(SVG_NS, "defs");
    const grad = document.createElementNS(SVG_NS, "linearGradient");
    grad.setAttribute("id", "path-grad");
    // userSpaceOnUse + viewBox 좌표(0~100)로 고정 — 기본(objectBoundingBox)은 경로가 완전히
    // 수직/수평이면(바운딩박스 폭 또는 높이가 0) 그라디언트가 특이(degenerate)해져 선 자체가
    // 안 보이는 버그가 있었다(정서 궤적 기본값이 전부 밝기 50%라 세로 직선이 되는 케이스).
    grad.setAttribute("gradientUnits", "userSpaceOnUse");
    grad.setAttribute("x1", "0"); grad.setAttribute("x2", "100");
    grad.setAttribute("y1", "0"); grad.setAttribute("y2", "0");
    const s1 = document.createElementNS(SVG_NS, "stop");
    s1.setAttribute("offset", "0%"); s1.setAttribute("stop-color", "#7c6cff");
    const s2 = document.createElementNS(SVG_NS, "stop");
    s2.setAttribute("offset", "100%"); s2.setAttribute("stop-color", "#ff6cc4");
    grad.append(s1, s2);
    defs.append(grad);
    path.setAttribute("stroke", "url(#path-grad)");

    // 희소 셀 오버레이 — 지도 게임의 "못 가는 지형"(크레이터/물가) 관용구를 빌려 빗금
    // 패턴으로 표시한다(2026-08-15 피드백 — 색 블러 얼룩은 무슨 뜻인지 안 와닿는다는 지적,
    // 재차 "막는 건 아니고 표현만"이라는 요청). 클릭·드래그를 막지는 않는다(pointer-events:none
    // 그대로) — 순수 시각적 힌트.
    const hatchPattern = document.createElementNS(SVG_NS, "pattern");
    hatchPattern.setAttribute("id", "sparse-hatch");
    hatchPattern.setAttribute("patternUnits", "userSpaceOnUse");
    hatchPattern.setAttribute("width", "3");
    hatchPattern.setAttribute("height", "3");
    hatchPattern.setAttribute("patternTransform", "rotate(45)");
    const hatchLine = document.createElementNS(SVG_NS, "line");
    hatchLine.setAttribute("x1", "0"); hatchLine.setAttribute("y1", "0");
    hatchLine.setAttribute("x2", "0"); hatchLine.setAttribute("y2", "3");
    hatchLine.setAttribute("class", "sparse-hatch-line");
    hatchPattern.appendChild(hatchLine);
    defs.append(hatchPattern);

    // gridG 앞에 삽입해서 그리드가 위에 보이도록
    const densityG = document.createElementNS(SVG_NS, "g");
    densityG.setAttribute("class", "map-density");
    if (featureStats && featureStats.map_2d) {
      const { grid, bins } = featureStats.map_2d;
      const maxCount = Math.max(1, ...grid.flat());
      for (let row = 0; row < bins; row++) {
        for (let col = 0; col < bins; col++) {
          const count = grid[row][col];
          const ratio = count / maxCount;
          // 희소 셀만 빗금으로 강조 — 밀도 있는 셀은 완전히 투명하게 둬서 기존 파스텔
          // 배경(정서 사분면)과 안 겹치게 한다(사용자 결정: 전체 히트맵이 아니라 "빈 곳만" 표시).
          if (count > 2 && ratio > 0.15) continue;
          const rect = document.createElementNS(SVG_NS, "rect");
          const x0 = toMapPct(col / bins), x1 = toMapPct((col + 1) / bins);
          const y0 = toMapPct(1 - (row + 1) / bins), y1 = toMapPct(1 - row / bins);
          rect.setAttribute("x", String(x0));
          rect.setAttribute("y", String(y0));
          rect.setAttribute("width", String(x1 - x0));
          rect.setAttribute("height", String(y1 - y0));
          rect.setAttribute("fill", "url(#sparse-hatch)");
          rect.setAttribute("class", "map-density-cell" + (count === 0 ? " empty" : ""));
          densityG.appendChild(rect);
        }
      }
    }

    mapSvgEl.append(defs, densityG, gridG, path);

    mapPadEl.querySelectorAll(".stage-node").forEach((n) => n.remove());
    mapNodeEls = stageModel.segments.map((s, i) => {
      const node = document.createElement("div");
      node.className = "stage-node";
      node.textContent = String(i + 1);
      const val = document.createElement("span");
      val.className = "node-val";
      node.append(val);
      mapPadEl.appendChild(node);
      bindMapDrag(node, i);
      node.addEventListener("pointerenter", () => setLinked(i));
      node.addEventListener("pointerleave", () => setLinked(-1));
      return node;
    });
  }

  function toXY(s) {
    return { x: toMapPct(s.valence), y: toMapPct(1 - s.energy) };
  }

  function updateMap() {
    const path = document.getElementById("map-path-line");
    const pts = stageModel.segments.map(toXY);
    let d = `M ${pts[0].x} ${pts[0].y}`;
    for (let i = 1; i < pts.length; i++) d += ` L ${pts[i].x} ${pts[i].y}`;
    path.setAttribute("d", d);

    stageModel.segments.forEach((s, i) => {
      const { x, y } = toXY(s);
      const node = mapNodeEls[i];
      node.style.left = `${x}%`;
      node.style.top = `${y}%`;
      node.querySelector(".node-val").textContent =
        t("map.nodeVal", { v: Math.round(s.valence * 100), e: Math.round(s.energy * 100) });
    });
  }

  function bindMapDrag(node, i) {
    node.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      node.setPointerCapture(e.pointerId);
      node.classList.add("dragging");
      const move = (ev) => {
        stageTouched = true;
        const r = mapPadEl.getBoundingClientRect();
        const fx = fromMapPct(((ev.clientX - r.left) / r.width) * 100);
        const fy = fromMapPct(((ev.clientY - r.top) / r.height) * 100);
        stageModel.segments[i].valence = fx;
        stageModel.segments[i].energy = clamp01(1 - fy);
        updateMap();
      };
      const up = () => {
        node.classList.remove("dragging");
        node.removeEventListener("pointermove", move);
        node.removeEventListener("pointerup", up);
      };
      node.addEventListener("pointermove", move);
      node.addEventListener("pointerup", up);
    });
  }

  // ── 시간 배분 바 ──────────────────────────────────────────────────────────
  // "(1)-----(2)----(3)---" 형태: 구간 순번 동그라미 자체가 그 구간의 시작 경계에
  // 놓이고, 그 동그라미를 좌우로 끄는 것이 곧 경계 이동이다. (1)은 항상 0분(맨 앞)
  // 고정이라 드래그되지 않고, (2)부터는 바로 앞 구간과의 경계를 옮기는 핸들을 겸한다.
  let timebarSegEls = [], timebarNumEls = [];

  function buildTimebar() {
    timebarEl.innerHTML = "";
    const track = document.createElement("div");
    track.className = "timebar-track";
    timebarEl.appendChild(track);

    timebarSegEls = stageModel.segments.map((_, i) => {
      const seg = document.createElement("div");
      seg.className = "timebar-seg";
      seg.addEventListener("pointerenter", () => setLinked(i));
      seg.addEventListener("pointerleave", () => setLinked(-1));
      timebarEl.appendChild(seg);
      return seg;
    });
    timebarNumEls = stageModel.segments.map((_, i) => {
      const num = document.createElement("span");
      num.className = "timebar-num";
      num.textContent = String(i + 1);
      if (i === 0) {
        num.classList.add("fixed");
      } else {
        num.classList.add("draggable");
        bindBoundaryDrag(num, i - 1);
      }
      timebarEl.appendChild(num);
      return num;
    });

    timebarTicksEl.innerHTML = "";
    const timebarTickEls = stageModel.segments.map((_, i) => {
      const tick = document.createElement("span");
      tick.className = "timebar-tick";
      timebarTicksEl.appendChild(tick);
      return tick;
    });
    const lastTick = document.createElement("span");
    lastTick.className = "timebar-tick";
    timebarTicksEl.appendChild(lastTick);
    timebarTickEls.push(lastTick);
    const unit = document.createElement("span");
    unit.className = "timebar-unit";
    unit.textContent = t("common.minuteUnit");
    timebarTicksEl.appendChild(unit);
  }

  function updateTimebar() {
    const { cum } = centers();
    stageModel.segments.forEach((s, i) => {
      const seg = timebarSegEls[i];
      seg.style.left = `${cum[i] * 100}%`;
      seg.style.width = `${s.width * 100}%`;
      timebarNumEls[i].style.left = `${cum[i] * 100}%`;
    });

    const timebarTickEls = timebarTicksEl.querySelectorAll(".timebar-tick");
    cum.forEach((c, i) => {
      const tick = timebarTickEls[i];
      tick.style.left = `${c * 100}%`;
      tick.style.transform = i === 0 ? "translateX(0)" : i === cum.length - 1 ? "translateX(-100%)" : "translateX(-50%)";
      tick.textContent = String(Math.round(c * stageModel.totalMinutes));
    });
  }

  function bindBoundaryDrag(handle, j) {
    handle.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      handle.setPointerCapture(e.pointerId);
      handle.classList.add("dragging");
      const move = (ev) => {
        stageTouched = true;
        const minFrac = MIN_WIDTH_MIN / stageModel.totalMinutes;
        const r = timebarEl.getBoundingClientRect();
        const fx = clamp01((ev.clientX - r.left) / r.width);
        const segs = stageModel.segments;
        const leftFixed = segs.slice(0, j).reduce((a, s) => a + s.width, 0);
        const rightFixed = segs.slice(j + 2).reduce((a, s) => a + s.width, 0);
        const b = Math.max(leftFixed + minFrac, Math.min(fx, 1 - rightFixed - minFrac));
        segs[j].width = b - leftFixed;
        segs[j + 1].width = 1 - rightFixed - b;
        updateAllParamCharts();
        updateTimebar();
      };
      const up = () => {
        handle.classList.remove("dragging");
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up);
    });
  }

  function setLinked(i) {
    mapNodeEls.forEach((n, j) => n.classList.toggle("linked", j === i));
    timebarSegEls.forEach((seg, j) => seg.classList.toggle("linked", j === i));
    timebarNumEls.forEach((num, j) => num.classList.toggle("linked", j === i));
    impressionInputEls.forEach((el, j) => el.classList.toggle("linked", j === i));
    impressionBadgeEls.forEach((el, j) => el.classList.toggle("linked", j === i));
    impressionBandToggleEls.forEach((el, j) => el.classList.toggle("linked", j === i));
  }

  // ── 구간별 가사 감상(선택, 프로토타입) ──────────────────────────────────────
  // "[①] 구간 [입력창]" 형태로 구간마다 한 줄씩 세로로 나열. 배지는 정서 지도(.stage-node)·
  // 타임바(.timebar-num)와 같은 동그라미 순번 스타일(.impression-badge)을 재사용.
  let impressionInputEls = [];
  let impressionBadgeEls = [];
  // placeholder용 예시 문구 — 빈 입력창이 "가사 감상(선택)"처럼 막연하지 않고, 어떤 식으로
  // 적으면 되는지 감이 오도록 구간 순서대로 다른 예시를 보여준다.
  const IMPRESSION_PLACEHOLDER_EXAMPLES = tArr("options.impressionExamples");

  function buildImpressionRow() {
    impressionRowEl.innerHTML = "";
    impressionBadgeEls = [];
    impressionBandToggleEls = [];
    impressionBandPopupEls = [];
    openBandPopupIndex = -1; // 재렌더(구간 추가/삭제 등) 시 이전 열림 상태는 무의미해짐
    impressionInputEls = stageModel.segments.map((s, i) => {
      const item = document.createElement("div");
      item.className = "impression-item";
      const badge = document.createElement("span");
      badge.className = "impression-badge";
      badge.textContent = String(i + 1);
      impressionBadgeEls.push(badge);
      const label = document.createElement("span");
      label.className = "impression-item-label";
      label.textContent = t("options.impressionItemLabel");
      const input = document.createElement("input");
      input.type = "text";
      input.className = "impression-input";
      input.maxLength = 100;
      input.placeholder = `ex. ${IMPRESSION_PLACEHOLDER_EXAMPLES[i % IMPRESSION_PLACEHOLDER_EXAMPLES.length]}`;
      input.value = s.impression || "";
      input.addEventListener("input", () => {
        stageTouched = true;
        stageModel.segments[i].impression = input.value;
      });
      input.addEventListener("pointerenter", () => setLinked(i));
      input.addEventListener("pointerleave", () => setLinked(-1));

      // 구간별 "밴드 고정" 토글+팝업 — 감성 설정 텍스트박스 오른쪽에 배치(사용자 제안).
      // 전역 밴드 필터와 별개로, 이 구간만 특정 밴드(1개 이상)로 고정하고 싶을 때 쓴다.
      const bandWrap = document.createElement("div");
      bandWrap.className = "impression-band-wrap";
      const bandToggle = document.createElement("button");
      bandToggle.type = "button";
      bandToggle.className = "impression-band-toggle";
      bandToggle.classList.toggle("on", (s.bands || []).length > 0);
      const dot = document.createElement("span");
      dot.className = "indicator-dot";
      bandToggle.append(dot, document.createTextNode(t("options.bandFix")));
      const popup = document.createElement("div");
      popup.className = "impression-band-popup hidden";
      renderBandPopupOptions(popup, i);
      bandToggle.addEventListener("click", (e) => {
        e.stopPropagation();
        const wasOpen = openBandPopupIndex === i;
        closeBandPopup();
        if (!wasOpen) {
          renderBandPopupOptions(popup, i); // 팝업 열 때마다 최신 전역 필터 반영해 다시 그림
          popup.classList.remove("hidden");
          openBandPopupIndex = i;
        }
      });
      bandToggle.addEventListener("pointerenter", () => setLinked(i));
      bandToggle.addEventListener("pointerleave", () => setLinked(-1));
      bandWrap.append(bandToggle, popup);
      impressionBandToggleEls.push(bandToggle);
      impressionBandPopupEls.push(popup);

      item.append(badge, label, input, bandWrap);
      impressionRowEl.appendChild(item);
      return input;
    });
  }

  function updateImpressionRow() {
    stageModel.segments.forEach((s, i) => {
      // 입력 중(포커스)인 칸은 값을 되쓰지 않는다 — 드래그 등으로 다시 그려질 때 커서 위치 보존.
      if (document.activeElement !== impressionInputEls[i]) {
        impressionInputEls[i].value = s.impression || "";
      }
      updateBandToggleIndicator(i);
    });
  }

  // ── 고급 설정 그래프 ──────────────────────────────────────────────────────
  let paramCharts = [];

  function buildParamGraphs() {
    paramGraphsEl.innerHTML = "";
    paramCharts = PARAM_DEFS.map(({ key, label, desc }) => {
      const wrap = document.createElement("div");
      wrap.className = "param-graph";

      const head = document.createElement("div");
      head.className = "param-head";
      const strong = document.createElement("strong");
      strong.textContent = label;
      head.append(strong);

      const descEl = document.createElement("ul");
      descEl.className = "field-note";
      const descLi = document.createElement("li");
      descLi.textContent = desc;
      descEl.appendChild(descLi);
      // 추천 구간 범례 — 5개 슬라이더 전부 같은 문구를 공유한다(2026-08-15).
      const recommendHintLi = document.createElement("li");
      recommendHintLi.textContent = t("options.recommendBandHint");
      descEl.appendChild(recommendHintLi);

      const plotRow = document.createElement("div");
      plotRow.className = "plot-row";
      const yAxis = document.createElement("div");
      yAxis.className = "y-axis";
      const yTop = document.createElement("span"); yTop.className = "y-tick"; yTop.textContent = "100";
      const yBot = document.createElement("span"); yBot.className = "y-tick"; yBot.textContent = "0";
      yAxis.append(yTop, yBot);

      const plot = document.createElement("div");
      plot.className = "plot";
      const svg = document.createElementNS(SVG_NS, "svg");
      svg.setAttribute("viewBox", "0 0 100 100");
      svg.setAttribute("preserveAspectRatio", "none");
      svg.setAttribute("class", "graph-svg");
      const gridG = document.createElementNS(SVG_NS, "g");
      [0, 0.5, 1].forEach((v) => {
        const ln = document.createElementNS(SVG_NS, "line");
        const y = valToY(v);
        ln.setAttribute("x1", "0"); ln.setAttribute("x2", "100");
        ln.setAttribute("y1", String(y)); ln.setAttribute("y2", String(y));
        ln.setAttribute("class", v === 0 || v === 1 ? "grid grid-edge" : "grid");
        gridG.append(ln);
      });
      const boundaryG = document.createElementNS(SVG_NS, "g");
      const boundaryLines = stageModel.segments.slice(1).map(() => {
        const ln = document.createElementNS(SVG_NS, "line");
        ln.setAttribute("y1", "0"); ln.setAttribute("y2", "100");
        ln.setAttribute("class", "grid-boundary");
        boundaryG.append(ln);
        return ln;
      });
      const area = document.createElementNS(SVG_NS, "path"); area.setAttribute("class", "graph-area");
      const curve = document.createElementNS(SVG_NS, "path"); curve.setAttribute("class", "graph-curve");

      // 추천 구간 밴드 — 예전엔 희소 구간마다 경고색 rect를 깔았는데, "이 슬라이더들은
      // 실제로는 전부 단봉분포(값 하나에 정점, 양옆은 완만히 줄어듦)라 희소 구간이 꼬리에만
      // 있고, 경고색 여러 조각이 마치 서로 다른 두 그룹처럼 오해된다는 피드백(2026-08-15)이
      // 있었다. 그래서 관점을 뒤집어 "후보가 충분한 연속 구간"을 초록 밴드 하나로 양성적으로
      // 보여준다(카메라 노출계·오디오 미터의 "적정 구간" 표시와 같은 관용구).
      const recommendG = document.createElementNS(SVG_NS, "g");
      recommendG.setAttribute("class", "param-recommend");
      if (featureStats && featureStats.histograms && featureStats.histograms[key]) {
        const counts = featureStats.histograms[key];
        const bins = featureStats.bins_1d;
        const maxCount = Math.max(1, ...counts);
        const isDense = counts.map((count) => count > 2 && count / maxCount > 0.15);
        const firstDense = isDense.indexOf(true);
        const lastDense = isDense.lastIndexOf(true);
        if (firstDense !== -1) {
          const rect = document.createElementNS(SVG_NS, "rect");
          const y0 = valToY((lastDense + 1) / bins), y1 = valToY(firstDense / bins);
          rect.setAttribute("x", "0");
          rect.setAttribute("y", String(y0));
          rect.setAttribute("width", "100");
          rect.setAttribute("height", String(y1 - y0));
          rect.setAttribute("class", "param-recommend-band");
          recommendG.appendChild(rect);
        }
      }

      // recommendG는 area(곡선 아래 보라색 채움) 뒤에 그린다 — 앞에 두면 area가 덮어써서
      // 초록 밴드가 거의 안 보였다(2026-08-15 실측 발견. area는 곡선~바닥까지 항상 넓게
      // 채우므로 기본값 근처에서는 recommend 밴드 대부분이 가려짐).
      svg.append(gridG, boundaryG, area, recommendG, curve);
      plot.append(svg);

      const dotEls = stageModel.segments.map((_, i) => {
        const dot = document.createElement("div");
        dot.className = "param-dot";
        dot.append(document.createTextNode(String(i + 1)));
        const val = document.createElement("span");
        val.className = "param-dot-val";
        dot.append(val);
        plot.appendChild(dot);
        return dot;
      });

      plotRow.append(yAxis, plot);
      wrap.append(head, descEl, plotRow);
      paramGraphsEl.appendChild(wrap);

      const chart = { key, plot, curve, area, boundaryLines, dotEls };
      dotEls.forEach((dot, i) => bindParamDotDrag(dot, chart, i));
      return chart;
    });
  }

  function updateParamChart(chart) {
    const { key, curve, area, boundaryLines, dotEls } = chart;
    const { cum, mid } = centers();
    const pts = [{ x: 0, y: valToY(stageModel.segments[0][key]) }];
    stageModel.segments.forEach((s, i) => pts.push({ x: mid[i] * 100, y: valToY(s[key]) }));
    pts.push({ x: 100, y: valToY(stageModel.segments[stageModel.segments.length - 1][key]) });
    const d = smoothPath(pts);
    curve.setAttribute("d", d);
    area.setAttribute("d", `${d} L 100 100 L 0 100 Z`);

    dotEls.forEach((dot, i) => {
      dot.style.left = `${mid[i] * 100}%`;
      dot.style.top = `${valToY(stageModel.segments[i][key])}%`;
      dot.querySelector(".param-dot-val").textContent = Math.round(stageModel.segments[i][key] * 100);
    });
    boundaryLines.forEach((ln, j) => {
      ln.setAttribute("x1", String(cum[j + 1] * 100));
      ln.setAttribute("x2", String(cum[j + 1] * 100));
    });
  }

  function updateAllParamCharts() { paramCharts.forEach(updateParamChart); }

  function bindParamDotDrag(dot, chart, i) {
    dot.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      dot.setPointerCapture(e.pointerId);
      dot.classList.add("dragging");
      const move = (ev) => {
        stageTouched = true;
        const r = chart.plot.getBoundingClientRect();
        const fy = clamp01((ev.clientY - r.top) / r.height);
        stageModel.segments[i][chart.key] = yToVal(fy);
        updateParamChart(chart);
      };
      const up = () => {
        dot.classList.remove("dragging");
        dot.removeEventListener("pointermove", move);
        dot.removeEventListener("pointerup", up);
      };
      dot.addEventListener("pointermove", move);
      dot.addEventListener("pointerup", up);
    });
  }

  // 모든 내부 함수·변수 정의 후, 마지막에 그래프 렌더링 호출
  buildAllGraphics();
}

function bindDrag(node, graph, onMove) {
  node.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    node.setPointerCapture(e.pointerId);
    node.classList.add("dragging");
    const move = (ev) => {
      stageTouched = true;
      const r = graph.getBoundingClientRect();
      onMove(clamp01((ev.clientX - r.left) / r.width), clamp01((ev.clientY - r.top) / r.height));
    };
    const up = () => {
      node.classList.remove("dragging");
      node.removeEventListener("pointermove", move);
      node.removeEventListener("pointerup", up);
    };
    node.addEventListener("pointermove", move);
    node.addEventListener("pointerup", up);
  });
}

function collectStages() {
  if (!stageTouched || !stageModel) return null;
  const total = stageModel.totalMinutes;
  return stageModel.segments.map((s) => ({
    energy: +s.energy.toFixed(3),
    minutes: Math.max(MIN_WIDTH_MIN, Math.round(s.width * total)),
    valence: +s.valence.toFixed(3),
    lufs_integrated: +s.lufs_integrated.toFixed(3),
    lra: +s.lra.toFixed(3),
    danceability_norm: +s.danceability_norm.toFixed(3),
    instr_stem_ratio: +s.instr_stem_ratio.toFixed(3),
    speech_median: +s.speech_median.toFixed(3),
    impression: (s.impression || "").trim() || null,
    bands: s.bands && s.bands.length ? s.bands : null,
  }));
}

// stages는 renderResult가 이미 실제 곡 배정 비율(width)까지 채워둔 lastStages를 넘겨받는다
// (에너지만 반영하고 나머지 6지표+감성문장을 0.5/빈 값으로 덮어쓰던 버그 수정 — 이제 이번
// 생성에 실제로 쓰인 값을 커스텀 모드 파라미터 UI에 그대로 반영한다).
function syncGraphToParams(params, stages) {
  if (stageTouched || !params) return;
  const total = params.target_minutes || (stageModel ? stageModel.totalMinutes : 60);
  let segments;
  if (Array.isArray(stages) && stages.length >= MIN_SEGMENTS) {
    const n = Math.max(MIN_SEGMENTS, Math.min(MAX_SEGMENTS, stages.length));
    segments = stages.slice(0, n).map((s) => {
      const e = s.energy != null ? s.energy : (typeof s.energy_target === "number" ? s.energy_target : 0.4);
      return {
        energy: clamp01(+e.toFixed(2)),
        width: s.width != null ? s.width : 1 / n,
        valence: s.valence != null ? +s.valence.toFixed(3) : 0.5,
        lufs_integrated: s.lufs_integrated != null ? +s.lufs_integrated.toFixed(3) : 0.5,
        lra: s.lra != null ? +s.lra.toFixed(3) : 0.5,
        danceability_norm: s.danceability_norm != null ? +s.danceability_norm.toFixed(3) : 0.5,
        instr_stem_ratio: s.instr_stem_ratio != null ? +s.instr_stem_ratio.toFixed(3) : 0.5,
        speech_median: s.speech_median != null ? +s.speech_median.toFixed(3) : 0.5,
        impression: s.impression || "",
        bands: s.bands && s.bands.length ? s.bands : [],
      };
    });
  } else {
    const n = Math.max(MIN_SEGMENTS, Math.min(MAX_SEGMENTS, params.stage_count || 3));
    const start = typeof params.start_energy === "number" ? params.start_energy : 0.3;
    const end = typeof params.end_energy === "number" ? params.end_energy : 0.7;
    segments = [];
    for (let i = 0; i < n; i++) {
      const energy = n === 1 ? start : start + ((end - start) * i) / (n - 1);
      segments.push({
        energy: clamp01(+energy.toFixed(2)),
        width: 1 / n,
        valence: 0.5,
        lufs_integrated: 0.5,
        lra: 0.5,
        danceability_norm: 0.5,
        instr_stem_ratio: 0.5,
        speech_median: 0.5,
        impression: "",
        bands: [],
      });
    }
  }
  stageModel = { totalMinutes: total, segments };
  renderStageGraph();
}

function clampInt(raw, lo, hi, dflt) { const n = parseInt(raw, 10); return Number.isNaN(n) ? dflt : Math.max(lo, Math.min(hi, n)); }

// 세부설정 버튼 이벤트 — 정적 버튼에 한 번만 붙인다(renderStageGraph()는 다시 그릴 때마다 호출되므로)
function initStageControls() {
  // 배경 토글
  const bgToggleButtons = bgToggleEl.querySelectorAll("button");
  bgToggleButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      mapPadEl.classList.remove("bg-current", "bg-quadrant", "bg-emoi");
      mapPadEl.classList.add(`bg-${btn.dataset.bg}`);
      bgToggleButtons.forEach((b) => b.classList.toggle("on", b === btn));
    });
  });

  // 구간 수 증가
  stagePlusBtn.addEventListener("click", () => {
    if (!stageModel || stageModel.segments.length >= MAX_SEGMENTS) return;
    const last = stageModel.segments[stageModel.segments.length - 1];
    const shrink = last.width / 2;
    last.width -= shrink;
    stageModel.segments.push({
      width: shrink,
      valence: clamp01(last.valence + 0.05),
      energy: clamp01(last.energy - 0.1),
      lufs_integrated: last.lufs_integrated,
      lra: last.lra,
      danceability_norm: last.danceability_norm,
      instr_stem_ratio: last.instr_stem_ratio,
      speech_median: last.speech_median,
      impression: "", // 새 구간은 빈 값(직전 구간 텍스트를 복사하면 오해를 살 수 있음)
      bands: [], // 밴드도 마찬가지로 직전 구간 값을 복사하지 않음
    });
    stageTouched = true;
    renderStageGraph();
  });

  // 구간 수 감소
  stageMinusBtn.addEventListener("click", () => {
    if (!stageModel || stageModel.segments.length <= MIN_SEGMENTS) return;
    const removed = stageModel.segments.pop();
    stageModel.segments[stageModel.segments.length - 1].width += removed.width;
    stageTouched = true;
    renderStageGraph();
  });

  // 시간 배분 균일화 — 구간별 재생시간(width)만 똑같이 맞추고, 정서 궤적·고급 설정 값은 그대로 둔다.
  const timebarEqualizeBtn = $("timebar-equalize");
  if (timebarEqualizeBtn) {
    timebarEqualizeBtn.addEventListener("click", () => {
      if (!stageModel) return;
      const n = stageModel.segments.length;
      stageModel.segments.forEach((s) => { s.width = 1 / n; });
      stageTouched = true;
      renderStageGraph();
    });
  }
}

// 희소 힌트용 feature stats 로드 — loadBands 패턴과 동일한 재시도 백오프
async function loadFeatureStats(attempt = 0) {
  try {
    const res = await fetch(`${API_BASE}/api/feature-stats`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    featureStats = data;
    // 이미 그래프가 그려졌으면(stageModel 존재) 새 hint 데이터로 재렌더
    if (stageModel) renderStageGraph();
  } catch (_) {
    if (attempt < 6) {
      setTimeout(() => loadFeatureStats(attempt + 1), 3000 * (attempt + 1));
    }
    // 최종 실패: featureStats = null 유지 → 힌트 안 그려짐 (no-op, nice-to-have)
  }
}

