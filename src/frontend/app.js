/* setlist-maker 프론트 — 요청 → 세트리스트 렌더 → YouTube 순차 자동재생 + umami 계측.
 * 백엔드 계약: architecture.md 스키마3 (POST /api/setlist, GET /api/health, 공통 에러 포맷).
 */
"use strict";

const API_BASE = (window.SETLIST_API_BASE || "http://localhost:8000").replace(/\/$/, "");
const AVG_SONG_SECONDS = 213; // duration 미확보 시 폴백(백엔드와 동일 가정).

// ── DOM ──────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const form = $("request-form");
const submitBtn = $("submit-btn");
const loadingEl = $("loading");
const errorEl = $("error");
const resultEl = $("result");
const summaryEl = $("summary");
const tracklistEl = $("tracklist");
const nowPlayingEl = $("now-playing");

// ── 재생 상태 ─────────────────────────────────────────────────────────────────
let picks = [];
let current = -1;
let estimatedTotal = 0;
let playedSeconds = 0;
let halfFired = false;
let errorSkips = 0; // 재생불가 영상 연속 스킵 가드(무한 루프 방지)
let loadedVideoId = null; // 플레이어에 로드/큐된 영상 id — 편집 후 재생 정합에 사용
let playbackStarted = false; // 첫 PLAYING 이후 true — 편집 시 cue(정지) vs load(자동재생) 선택
const editHistory = []; // 편집(순서이동·제거) 되돌리기 스택 — Ctrl+Z

// ── umami 계측(스크립트 미설치 시 무해) ─────────────────────────────────────────
function track(name, data) {
  try {
    if (window.umami && typeof window.umami.track === "function") window.umami.track(name, data);
  } catch (_) {/* 계측 실패는 UX에 영향 주지 않음 */}
}

// ── 요청 ─────────────────────────────────────────────────────────────────────
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const prompt = $("prompt").value.trim();
  if (!prompt) return;

  const body = { prompt };
  const minutes = parseInt($("target-minutes").value, 10);
  const stageCount = parseInt($("stage-count").value, 10);
  if (!Number.isNaN(minutes)) body.target_minutes = minutes;
  if (!Number.isNaN(stageCount)) body.stage_count = stageCount;

  const bands = collectBands();
  if (bands.length) body.bands = bands;
  const customStages = collectStages();
  if (customStages) body.stages = customStages;
  body.include_original = $("inc-original").checked;
  body.include_cover = $("inc-cover").checked;

  showLoading(true);
  hide(errorEl);
  hide(resultEl);

  try {
    const res = await fetch(`${API_BASE}/api/setlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (data && data.error && data.error.message) || `요청 실패 (HTTP ${res.status})`;
      throw new Error(msg);
    }
    renderResult(data);
  } catch (err) {
    const offline = err instanceof TypeError; // fetch 자체 실패(네트워크/CORS)
    showError(offline
      ? "백엔드에 연결하지 못했어요. 서버가 켜져 있는지, API 주소가 맞는지 확인해 주세요."
      : err.message);
  } finally {
    showLoading(false);
  }
});

function showLoading(on) {
  submitBtn.disabled = on;
  toggle(loadingEl, on);
}
function showError(message) {
  errorEl.textContent = "⚠️ " + message;
  show(errorEl);
}

// ── 설정: 밴드 필터 · 단계 직접 지정 (§5-1) ────────────────────────────────────
const bandListEl = $("band-list");
const stageEditorEl = $("stage-editor");
let stageTouched = false; // 사용자가 그래프를 조정했는지 — 조정 전엔 LLM 에너지 자동 사용

// 사용자가 '직접' 체크한 밴드만 요청 간 지속한다. 프롬프트 자동감지 밴드는 매 요청 일회성이어야
// 하므로(자연어 요청 = 매번 새 의도), 체크박스의 시각 상태와 분리해 별도 집합으로 추적한다.
// 이 집합은 오직 사용자의 change 이벤트로만 갱신 — 프로그램적 .checked 대입은 change를 발생시키지
// 않으므로 syncBandChecks가 여기 섞이지 않는다(요청 간 밴드 누적 버그의 근본 차단).
const manualBands = new Set();

async function loadBands() {
  try {
    const res = await fetch(`${API_BASE}/api/bands`);
    const data = await res.json();
    renderBands(data.bands || []);
  } catch (_) {
    bandListEl.textContent = "밴드 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).";
  }
}

function renderBands(bands) {
  bandListEl.replaceChildren();
  if (!bands.length) { bandListEl.textContent = "밴드 없음"; return; }
  for (const b of bands) {
    const label = document.createElement("label");
    label.className = "band-item";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = b.band;
    cb.className = "band-cb";
    // 사용자가 직접 토글한 것만 manualBands에 반영(요청 간 지속 대상). syncBandChecks의
    // 프로그램적 대입은 change를 발생시키지 않으므로 자동감지분은 여기 들어오지 않는다.
    cb.addEventListener("change", () => {
      if (cb.checked) manualBands.add(cb.value);
      else manualBands.delete(cb.value);
    });
    const span = document.createElement("span");
    span.textContent = `${prettyBand(b.band)} (${b.count})`;
    label.append(cb, span);
    bandListEl.appendChild(label);
  }
}

function collectBands() {
  // 수동 선택분만 요청에 싣는다. 프롬프트 자동감지 밴드는 백엔드가 이번 프롬프트에서 매번 새로
  // 더하므로 프론트가 재전송하면 안 된다(이전 요청 밴드 누적 방지).
  return [...manualBands];
}

$("band-clear").addEventListener("click", () => {
  manualBands.clear();
  document.querySelectorAll(".band-cb:checked").forEach((c) => (c.checked = false));
});

// 시간×에너지 텐션 그래프 편집기 (§5-1a). 점=에너지(상하 드래그), 경계=구간 길이(좌우 드래그).
const SVG_NS = "http://www.w3.org/2000/svg";
const PAD_TOP = 10;      // 그래프 상하 여백(뷰박스 0~100 기준)
const PAD_BOTTOM = 12;
const MIN_WIDTH = 0.08;  // 구간 최소 폭(전체 대비)

let stageModel = null; // { totalMinutes, segments: [{energy(0~1), width(합=1)}] }

$("stage-count").addEventListener("input", () => {
  initStageModel(); stageTouched = false; renderStageGraph();
});
$("target-minutes").addEventListener("input", () => {
  if (stageModel) {
    stageModel.totalMinutes = clampInt($("target-minutes").value, 10, 180, 60);
    renderStageGraph();
  }
});

function initStageModel() {
  const n = clampInt($("stage-count").value, 2, 5, 3);
  const total = clampInt($("target-minutes").value, 10, 180, 60);
  const segments = [];
  for (let i = 0; i < n; i++) {
    segments.push({ energy: +(0.3 + (0.55 * i) / (n - 1)).toFixed(2), width: 1 / n });
  }
  stageModel = { totalMinutes: total, segments };
}

function energyToY(energy) { return PAD_TOP + (1 - energy) * (100 - PAD_TOP - PAD_BOTTOM); }
function yToEnergy(frac) { return clamp01(1 - (frac * 100 - PAD_TOP) / (100 - PAD_TOP - PAD_BOTTOM)); }

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

function renderStageGraph() {
  if (!stageModel) initStageModel();
  stageEditorEl.replaceChildren();

  // 축 프레임: [Y축 라벨][플롯] / [여백][X축 시간 라벨]
  const plotRow = elDiv("plot-row");
  const yAxis = elDiv("y-axis");
  const yTop = elDiv("y-tick"); yTop.textContent = "높음";
  const yTitle = elDiv("y-axis-title"); yTitle.textContent = "에너지";
  const yBot = elDiv("y-tick"); yBot.textContent = "낮음";
  yAxis.append(yTop, yTitle, yBot);

  const plot = elDiv("plot");
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 100 100");
  svg.setAttribute("preserveAspectRatio", "none");
  svg.setAttribute("class", "graph-svg");
  const gridG = document.createElementNS(SVG_NS, "g");
  [0, 0.25, 0.5, 0.75, 1].forEach((e) => {
    const ln = document.createElementNS(SVG_NS, "line");
    const y = energyToY(e);
    ln.setAttribute("x1", "0"); ln.setAttribute("x2", "100");
    ln.setAttribute("y1", String(y)); ln.setAttribute("y2", String(y));
    ln.setAttribute("class", e === 0 || e === 1 ? "grid grid-edge" : "grid");
    gridG.append(ln);
  });
  const area = document.createElementNS(SVG_NS, "path"); area.setAttribute("class", "graph-area");
  const curve = document.createElementNS(SVG_NS, "path"); curve.setAttribute("class", "graph-curve");
  svg.append(gridG, area, curve);
  plot.append(svg);

  const dots = stageModel.segments.map(() => {
    const dot = elDiv("energy-dot");
    dot.append(elDiv("dot-val"));
    return plot.appendChild(dot);
  });
  const handles = stageModel.segments.slice(1).map(() => plot.appendChild(elDiv("bound-handle")));
  plotRow.append(yAxis, plot);

  const xRow = elDiv("x-axis-row");
  xRow.append(elDiv("x-spacer"));
  const xAxis = elDiv("x-axis");
  xRow.append(xAxis);

  const hint = elDiv("graph-hint");
  hint.textContent = "● 점을 위·아래로 = 에너지  ·  ◆ 경계를 좌·우로 = 구간 길이";
  stageEditorEl.append(plotRow, xRow, hint);

  function update() {
    const segs = stageModel.segments, n = segs.length, total = stageModel.totalMinutes;
    const cum = [0];
    segs.forEach((s) => cum.push(cum[cum.length - 1] + s.width));
    const centers = segs.map((s, i) => (cum[i] + cum[i + 1]) / 2);

    const pts = [{ x: 0, y: energyToY(segs[0].energy) }];
    segs.forEach((s, i) => pts.push({ x: centers[i] * 100, y: energyToY(s.energy) }));
    pts.push({ x: 100, y: energyToY(segs[n - 1].energy) });
    const d = smoothPath(pts);
    curve.setAttribute("d", d);
    area.setAttribute("d", `${d} L 100 100 L 0 100 Z`);

    dots.forEach((dot, i) => {
      dot.style.left = `${centers[i] * 100}%`;
      dot.style.top = `${energyToY(segs[i].energy)}%`;
      dot.firstChild.textContent = segs[i].energy.toFixed(2);
    });
    handles.forEach((h, j) => { h.style.left = `${cum[j + 1] * 100}%`; });

    // X축 시간 눈금(구간 경계 = 누적 분)
    xAxis.replaceChildren();
    cum.forEach((c, i) => {
      const tick = elDiv("x-tick");
      tick.style.left = `${c * 100}%`;
      if (i === 0) tick.style.transform = "translateX(0)";
      else if (i === cum.length - 1) tick.style.transform = "translateX(-100%)";
      tick.textContent = String(Math.round(c * total));
      xAxis.append(tick);
    });
    const unit = elDiv("x-unit"); unit.textContent = "분"; xAxis.append(unit);
  }

  dots.forEach((dot, i) => bindDrag(dot, plot, (fx, fy) => {
    stageModel.segments[i].energy = yToEnergy(fy);
    update();
  }));
  handles.forEach((handle, j) => bindDrag(handle, plot, (fx) => {
    const segs = stageModel.segments;
    const leftFixed = segs.slice(0, j).reduce((a, s) => a + s.width, 0);
    const rightFixed = segs.slice(j + 2).reduce((a, s) => a + s.width, 0);
    const b = clamp(fx, leftFixed + MIN_WIDTH, 1 - rightFixed - MIN_WIDTH);
    segs[j].width = b - leftFixed;
    segs[j + 1].width = 1 - rightFixed - b;
    update();
  }));

  update();
}

function bindDrag(node, graph, onMove) {
  node.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    node.setPointerCapture(e.pointerId);
    node.classList.add("dragging");
    const move = (ev) => {
      stageTouched = true; // 사용자가 그래프를 조정함 → 이후 요청에 이 아크를 적용
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
    minutes: Math.max(1, Math.round(s.width * total)),
  }));
}

function elDiv(cls) { const d = document.createElement("div"); d.className = cls; return d; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function clamp01(v) { return Math.max(0, Math.min(1, v)); }
function clampInt(raw, lo, hi, dflt) { const n = parseInt(raw, 10); return Number.isNaN(n) ? dflt : Math.max(lo, Math.min(hi, n)); }

// 응답 후 그래프를 LLM 해석 아크로 동기화(사용자가 드래그로 조정하기 전까지만).
// → 그래프가 요청을 '반영'만 하고 간섭하지 않는다(코멘트 #1 대안 2).
function syncGraphToParams(params) {
  if (stageTouched || !params) return;
  const n = Math.max(2, Math.min(5, params.stage_count || 3));
  const start = typeof params.start_energy === "number" ? params.start_energy : 0.3;
  const end = typeof params.end_energy === "number" ? params.end_energy : 0.7;
  const total = params.target_minutes || (stageModel ? stageModel.totalMinutes : 60);
  const segments = [];
  for (let i = 0; i < n; i++) {
    const energy = n === 1 ? start : start + ((end - start) * i) / (n - 1);
    segments.push({ energy: clamp01(+energy.toFixed(2)), width: 1 / n });
  }
  stageModel = { totalMinutes: total, segments };
  renderStageGraph();
}

loadBands();
initStageModel();
renderStageGraph(); // 그래프는 세부설정에서 상시 표시(토글 없음)

// ── 렌더 ─────────────────────────────────────────────────────────────────────
function renderResult(data) {
  picks = data.picks || [];
  estimatedTotal = data.estimated_total_seconds || 0;
  playedSeconds = 0;
  halfFired = false;
  errorSkips = 0;
  current = -1;
  playbackStarted = false;
  loadedVideoId = null;
  editHistory.length = 0; // 새 플레이리스트 → 편집 히스토리 리셋

  if (!picks.length) {
    showError("조건에 맞는 곡을 찾지 못했어요. 요청을 조금 바꿔 보세요.");
    return;
  }

  renderSummary(data);
  renderTracklist(picks);
  syncBandChecks(data.applied_bands); // 적용된 밴드(프롬프트 자동감지 포함)를 체크박스에 반영
  syncGraphToParams(data.params); // 그래프에 이번 해석 아크 반영(미조정 시)
  show(resultEl);

  track("playlist_created", { count: picks.length, minutes: Math.round(estimatedTotal / 60) });

  startPlayback();
}

function renderSummary(data) {
  const p = data.params || {};
  summaryEl.replaceChildren();

  const interp = document.createElement("p");
  interp.className = "interp";
  interp.textContent = p.interpretation_summary || "요청을 해석해 세트리스트를 구성했어요.";
  summaryEl.appendChild(interp);

  const meta = document.createElement("div");
  meta.className = "meta";
  const mins = Math.round(estimatedTotal / 60);
  const chips = [
    `밝기 ${fmtSigned(p.brightness)}`,
    `에너지 ${fmtNum(p.start_energy)} → ${fmtNum(p.end_energy)}`,
    `${p.stage_count}단계`,
    `${picks.length}곡`,
    `약 ${mins}분`,
  ];
  for (const c of chips) {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = c;
    meta.appendChild(span);
  }
  summaryEl.appendChild(meta);
}

function renderTracklist(list) {
  tracklistEl.replaceChildren();
  list.forEach((p, i) => {
    const li = document.createElement("li");
    li.className = "track";
    li.dataset.index = String(i);
    li.addEventListener("click", () => playSong(i, false));

    const pos = document.createElement("div");
    pos.className = "pos";
    pos.textContent = String(i + 1);

    const bodyEl = document.createElement("div");
    bodyEl.className = "body";

    const title = document.createElement("div");
    title.className = "title";
    title.textContent = p.song;

    const band = document.createElement("div");
    band.className = "band";
    band.textContent = prettyBand(p.band);

    const reason = document.createElement("div");
    reason.className = "reason";
    reason.textContent = (p.reason && p.reason.text) || "";

    const badges = document.createElement("div");
    badges.className = "badges";
    const h = p.reason ? p.reason.harmonic : "";
    badges.appendChild(makeBadge(h, harmonicLabelKo(h)));
    badges.appendChild(makeBadge("", `에너지 ${fmtNum(p.energy)}`));
    badges.appendChild(makeBadge("", p.camelot));

    bodyEl.append(title, band, reason, badges);
    li.append(pos, bodyEl, makeTrackActions(li, i));
    li.appendChild(makeInserter(i + 1)); // 이 트랙 '다음'(배열 index i+1) 삽입점
    tracklistEl.appendChild(li);
  });
}

// 트랙 우측 액션 — 이동 핸들(상하 셰브런) · 제거(−). 행 호버 시 은은히 나타나는 고스트 버튼.
// 곡 추가(+)는 트랙 사이 인서터로 분리(makeInserter) — 더 직관적인 '사이 삽입'.
function makeTrackActions(li, index) {
  const actions = elDiv("track-actions");
  actions.addEventListener("click", (e) => e.stopPropagation()); // 행 클릭(재생) 방지

  const move = document.createElement("button");
  move.type = "button";
  move.className = "track-btn track-move";
  move.title = "잡고 위아래로 드래그해 순서 이동";
  move.setAttribute("aria-label", "순서 이동 (드래그)");
  move.innerHTML =
    '<svg viewBox="0 0 24 16" fill="none" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M5 6.5 L12 1.5 L19 6.5"/><path d="M5 9.5 L12 14.5 L19 9.5"/></svg>';
  move.addEventListener("pointerdown", (e) => startReorder(move, li, e));

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "track-btn track-remove";
  remove.title = "이 곡 제거";
  remove.setAttribute("aria-label", "곡 제거");
  remove.innerHTML =
    '<svg viewBox="0 0 16 16" aria-hidden="true">' +
    '<rect x="3" y="7" width="10" height="2" rx="1" fill="currentColor"/></svg>';
  remove.addEventListener("click", () => removeSong(index));

  actions.append(move, remove);
  return actions;
}

// 트랙 사이 삽입점(+): 트랙 아래 간격에 겹쳐 두고, 그 구역에 호버하면 중앙에 '+'가 떠오른다.
// atIndex = picks 배열의 삽입 위치(이 트랙 '다음' = index+1).
function makeInserter(atIndex) {
  const zone = elDiv("track-inserter");
  zone.addEventListener("click", (e) => e.stopPropagation()); // 행 클릭(재생) 방지
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "inserter-btn";
  btn.title = "여기에 곡 추가";
  btn.setAttribute("aria-label", "여기에 곡 추가");
  btn.innerHTML =
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" aria-hidden="true"><path d="M8 3.5 V12.5 M3.5 8 H12.5"/></svg>';
  btn.addEventListener("click", () => openSongPickerAt(atIndex));
  zone.append(btn);
  return zone;
}

function makeBadge(kind, label) {
  const b = document.createElement("span");
  b.className = "badge" + (kind ? " " + kind : "");
  b.textContent = label;
  return b;
}

// ── YouTube IFrame Player ─────────────────────────────────────────────────────
let player = null;
let ytReady = false;
let pendingStart = null;

window.onYouTubeIframeAPIReady = function () {
  ytReady = true;
  if (pendingStart) { const fn = pendingStart; pendingStart = null; fn(); }
};

function loadYouTubeApi() {
  if (window.YT && window.YT.Player) { ytReady = true; return; }
  if (document.getElementById("yt-api")) return;
  const s = document.createElement("script");
  s.id = "yt-api";
  s.src = "https://www.youtube.com/iframe_api";
  document.head.appendChild(s);
}

function startPlayback() {
  current = 0;
  loadedVideoId = picks[0].video_id;
  playbackStarted = false;
  highlight(0);
  updateNowPlaying(picks[0]);

  // song-sorter 검증 패턴: 빈 플레이어(생성자 videoId 없음) + autoplay 0.
  // 첫 곡은 cue만(자동재생 정책 위반 회피 — "An error occurred" 방지). 사용자가 ▶ 클릭 시 재생,
  // 이후 곡은 loadVideoById로 자동 전환(상호작용 이후이므로 자동재생 허용).
  const boot = () => {
    if (player && typeof player.cueVideoById === "function") {
      player.cueVideoById(picks[0].video_id);
      return;
    }
    player = new YT.Player("player", {
      height: "100%",
      width: "100%",
      playerVars: { autoplay: 0, modestbranding: 1, rel: 0, controls: 1, playsinline: 1 },
      events: {
        onReady: () => player.cueVideoById(picks[0].video_id),
        onStateChange: onPlayerStateChange,
        onError: onPlayerError,
      },
    });
  };

  if (ytReady) boot();
  else { pendingStart = boot; loadYouTubeApi(); }
}

function onPlayerStateChange(e) {
  if (e.data === YT.PlayerState.PLAYING) {
    errorSkips = 0; // 정상 재생 시 스킵 가드 리셋
    playbackStarted = true; // 이후 편집 시 load(자동재생) 허용
  } else if (e.data === YT.PlayerState.ENDED) {
    playedSeconds += safeDuration();
    maybeFireHalf();
    if (current + 1 < picks.length) playSong(current + 1, true);
  }
}

// 재생불가(삭제·임베드차단·연령제한·지역락) → 다음 곡 자동 스킵.
function onPlayerError(e) {
  const p = picks[current];
  console.warn("YouTube 재생 오류", e && e.data, "video", p && p.video_id);
  errorSkips += 1;
  if (errorSkips > picks.length) {
    showError("재생 가능한 영상을 찾지 못했어요. 다른 요청을 시도해 보세요.");
    return;
  }
  if (current + 1 < picks.length) {
    playSong(current + 1, true);
  } else {
    showError("이 영상은 재생할 수 없어요. 아래 'YouTube에서 열기'로 시청해 주세요.");
  }
}

function playSong(index, auto) {
  if (index < 0 || index >= picks.length) return;
  current = index;
  const p = picks[index];
  loadedVideoId = p.video_id;
  highlight(index);
  updateNowPlaying(p);
  // 사용자 클릭/자동 전환 — 상호작용 이후이므로 loadVideoById(자동재생) 사용.
  if (player && typeof player.loadVideoById === "function") player.loadVideoById(p.video_id);
  if (auto) track("song_advance", { position: p.position, idx: p.idx });
}

function safeDuration() {
  try {
    const d = player && player.getDuration ? player.getDuration() : 0;
    return d && d > 0 ? d : AVG_SONG_SECONDS;
  } catch (_) {
    return AVG_SONG_SECONDS;
  }
}

function maybeFireHalf() {
  if (halfFired || estimatedTotal <= 0) return;
  if (playedSeconds >= estimatedTotal * 0.5) {
    halfFired = true;
    track("playlist_half_played", { played_seconds: Math.round(playedSeconds) });
  }
}

// ── 플레이리스트 편집: 순서 이동 · 곡 제거 · 되돌리기 (사용자 제안 2026-07-11) ────────
// 편집은 클라이언트 `picks` 배열 조작 + 재렌더로 처리(백엔드 무관). 재생 흐름은 loadedVideoId
// 기준으로 정합해 편집 중에도 현재 곡이 유지되도록 한다.

// 순서 이동(floating drag): 핸들을 잡고 있는 동안 해당 곡이 마우스 Y를 따라 떠서 이동하고,
// 나머지 곡들은 부드럽게 자리를 비켜 '놓일 위치'를 미리 보여준다. 릴리즈 시 그 위치에 배치.
// DOM은 드래그 중 변형(transform)만 하고, 확정은 놓을 때 picks 배열 splice로 한 번에 반영한다.
function startReorder(handle, li, e) {
  e.preventDefault();
  e.stopPropagation();
  const rows = [...tracklistEl.children];
  const from = rows.indexOf(li);
  if (from < 0) return;

  // 드래그 시작 시점의 각 행 중심 Y를 기준으로 목표 인덱스를 계산(행 높이 가변 대응).
  const centers = rows.map((r) => { const b = r.getBoundingClientRect(); return b.top + b.height / 2; });
  const gap = li.getBoundingClientRect().height + trackGapPx(li); // 열릴 빈칸 크기 = 드래그 곡 높이
  const startY = e.clientY;
  let target = from;

  handle.setPointerCapture(e.pointerId);
  document.body.classList.add("reordering");
  li.classList.add("dragging");
  li.style.transition = "none"; // 잡은 곡은 커서를 지연 없이 따라옴
  rows.forEach((r) => { if (r !== li) r.style.transition = "transform 0.16s ease"; });

  const onMove = (ev) => {
    const dy = ev.clientY - startY;
    li.style.transform = `translateY(${dy}px)`;
    const draggedCenter = centers[from] + dy;
    let t = from;
    while (t > 0 && draggedCenter < centers[t - 1]) t--;
    while (t < rows.length - 1 && draggedCenter > centers[t + 1]) t++;
    if (t !== target) { target = t; applyReorderGap(rows, li, from, target, gap); }
  };
  const onUp = () => {
    try { handle.releasePointerCapture(e.pointerId); } catch (_) {/* 이미 해제됨 */}
    handle.removeEventListener("pointermove", onMove);
    handle.removeEventListener("pointerup", onUp);
    document.body.classList.remove("reordering");
    li.classList.remove("dragging");
    rows.forEach((r) => { r.style.transition = ""; r.style.transform = ""; });
    commitMove(from, target);
  };
  handle.addEventListener("pointermove", onMove);
  handle.addEventListener("pointerup", onUp);
}

// 행 사이 세로 간격(margin-bottom) px. 빈칸 애니메이션 크기 계산에 사용.
function trackGapPx(li) {
  const mb = parseFloat(getComputedStyle(li).marginBottom);
  return Number.isNaN(mb) ? 8 : mb;
}

// from→target 사이의 행들을 곡 한 칸만큼 밀어 '놓일 자리'를 시각적으로 연다.
function applyReorderGap(rows, li, from, target, gap) {
  rows.forEach((r, j) => {
    if (r === li) return;
    let shift = 0;
    if (target > from && j > from && j <= target) shift = -gap;
    else if (target < from && j >= target && j < from) shift = gap;
    r.style.transform = shift ? `translateY(${shift}px)` : "";
  });
}

// from 위치의 곡을 target 위치로 옮겨 picks를 확정하고 재렌더한다.
function commitMove(from, target) {
  if (from === target) return; // 제자리 — 변화 없음
  pushHistory();
  const [moved] = picks.splice(from, 1);
  picks.splice(target, 0, moved);
  renderTracklist(picks);
  reconcilePlayer();
  syncGraphToEdited();
}

// − 버튼: 해당 곡 제거. 재생 중이던 곡이면 reconcilePlayer가 다음 곡으로 넘긴다.
function removeSong(index) {
  if (index < 0 || index >= picks.length) return;
  pushHistory();
  picks.splice(index, 1);
  if (!picks.length) {
    hide(resultEl);
    showError("모든 곡을 제거했어요. 새 요청을 만들거나 되돌리기(Ctrl+Z) 하세요.");
    return;
  }
  renderTracklist(picks);
  reconcilePlayer();
  syncGraphToEdited();
}

// 편집 후 하이라이트·재생을 정합한다. 재생 중이던 곡이 남아 있으면 그 위치로 current를 옮기고,
// 제거됐으면 그 슬롯(클램프)의 곡으로 전환한다(재생 시작 전이면 cue, 이후면 load).
function reconcilePlayer() {
  const idx = picks.findIndex((p) => p.video_id === loadedVideoId);
  if (idx >= 0) {
    current = idx;
    highlight(current);
    updateNowPlaying(picks[current]);
    return;
  }
  current = Math.max(0, Math.min(current, picks.length - 1));
  const p = picks[current];
  loadedVideoId = p.video_id;
  highlight(current);
  updateNowPlaying(p);
  if (!player) return;
  if (playbackStarted && typeof player.loadVideoById === "function") player.loadVideoById(p.video_id);
  else if (typeof player.cueVideoById === "function") player.cueVideoById(p.video_id);
}

function pushHistory() {
  editHistory.push({ picks: picks.slice(), current });
  if (editHistory.length > 50) editHistory.shift();
}

// Ctrl/Cmd+Z — 직전 편집 상태(순서·구성) 복원. 텍스트 입력 중엔 브라우저 기본 되돌리기 양보.
document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey) return;
  if (e.key !== "z" && e.key !== "Z") return;
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (!editHistory.length) return;
  e.preventDefault();
  const prev = editHistory.pop();
  picks = prev.picks;
  current = prev.current;
  hide(errorEl);
  show(resultEl); // 전부 제거 후 되돌리기면 결과 다시 표시
  renderTracklist(picks);
  reconcilePlayer();
  syncGraphToEdited();
});

// 편집 후 에너지 그래프를 '실제 배치'로 갱신(옵션 기능). 편집된 순서를 n개 연속 그룹으로 나눠
// 각 그룹의 평균 에너지·곡수 비율로 세그먼트를 재구성한다. stageTouched는 건드리지 않아
// 다음 요청 입력으로 새지 않는다(그래프는 반영만, 코멘트 #1 대안 2 원칙 유지).
function syncGraphToEdited() {
  if (!stageModel || !picks.length) return;
  const n = Math.max(1, Math.min(stageModel.segments.length, picks.length));
  const segments = [];
  for (let i = 0; i < n; i++) {
    const startIdx = Math.floor((i * picks.length) / n);
    const endIdx = Math.floor(((i + 1) * picks.length) / n);
    const slice = picks.slice(startIdx, Math.max(endIdx, startIdx + 1));
    const mean = slice.reduce((a, p) => a + (typeof p.energy === "number" ? p.energy : 0), 0) / slice.length;
    segments.push({ energy: clamp01(+mean.toFixed(2)), width: (endIdx - startIdx) / picks.length });
  }
  const wsum = segments.reduce((a, s) => a + s.width, 0) || 1;
  segments.forEach((s) => (s.width = s.width / wsum));
  stageModel = { totalMinutes: stageModel.totalMinutes, segments };
  renderStageGraph();
}

// ── 곡 추가 미니 브라우저 (Phase 2) ─────────────────────────────────────────────
// + 버튼 → 밴드 셀렉터 + 곡 리스트에서 곡을 골라 그 트랙 '다음'에 삽입. /api/songs 1회 캐시.
const pickerEl = $("song-picker");
const pickerBandsEl = $("picker-bands");
const pickerSongsEl = $("picker-songs");
const pickerSearchEl = $("picker-search");
const pickerWhereEl = $("picker-where");
let allSongs = null;      // /api/songs 캐시(첫 열람 시 로드)
let insertAtIndex = 0;    // 삽입점(+)이 가리키는 picks 배열 위치
let pickerBand = null;    // 선택된 밴드(null=전체)

// bandori-song-sorter와 동일한 밴드 나열 순서 + 아이콘 애셋(assets/bands/<band>.png, 미포함은 뒤).
const BAND_ORDER = [
  "poppin_party", "afterglow", "pastel_palettes", "roselia",
  "hello_happy_world", "morfonica", "raise_a_suilen", "mygo",
  "ave_mujica", "mugendai_mutype", "millsage", "ikka_dumb_rock",
];
const BAND_ICON_BASE = "assets/bands";

function bandsInSelectorOrder(present) {
  const ordered = BAND_ORDER.filter((b) => present.includes(b));
  const rest = present.filter((b) => !BAND_ORDER.includes(b)).sort();
  return [...ordered, ...rest];
}

// 밴드 아이콘 img(로드 실패 시 _fallback로 1회 대체). bandori-song-sorter 애셋 재사용.
function makeBandIcon(band, cls) {
  const img = document.createElement("img");
  img.className = cls;
  img.src = `${BAND_ICON_BASE}/${band}.png`;
  img.alt = "";
  img.loading = "lazy";
  img.addEventListener("error", () => {
    if (img.dataset.fallback) return;
    img.dataset.fallback = "1";
    img.src = `${BAND_ICON_BASE}/_fallback.png`;
  });
  return img;
}

// 모달 열림 동안 메인 페이지 스크롤 잠금(스크롤 체이닝 방지). 스크롤바 폭만큼 보정해 레이아웃 밀림 방지.
function lockBodyScroll(lock) {
  if (lock) {
    const sw = window.innerWidth - document.documentElement.clientWidth;
    if (sw > 0) document.body.style.paddingRight = `${sw}px`;
    document.body.classList.add("modal-open");
  } else {
    document.body.classList.remove("modal-open");
    document.body.style.paddingRight = "";
  }
}

async function ensureSongs() {
  if (allSongs) return allSongs;
  const res = await fetch(`${API_BASE}/api/songs`);
  const data = await res.json();
  allSongs = data.songs || [];
  return allSongs;
}

async function openSongPickerAt(atIndex) {
  insertAtIndex = atIndex;
  pickerBand = null;
  pickerSearchEl.value = "";
  pickerWhereEl.textContent = atIndex <= 0 ? "맨 앞에 삽입" : `${atIndex}번 다음에 삽입`;
  show(pickerEl);
  lockBodyScroll(true);
  pickerBandsEl.replaceChildren();
  pickerSongsEl.replaceChildren();
  pickerSongsEl.textContent = "곡 목록 불러오는 중…";
  try {
    await ensureSongs();
    renderPickerBands();
    renderPickerSongs();
    pickerSearchEl.focus();
  } catch (_) {
    pickerSongsEl.textContent = "곡 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).";
  }
}

function closeSongPicker() { hide(pickerEl); lockBodyScroll(false); }

function renderPickerBands() {
  const counts = new Map();
  for (const s of allSongs) counts.set(s.band, (counts.get(s.band) || 0) + 1);
  pickerBandsEl.replaceChildren();
  pickerBandsEl.appendChild(pickerBandChip("전체", null, allSongs.length));
  for (const band of bandsInSelectorOrder([...counts.keys()])) {
    pickerBandsEl.appendChild(pickerBandChip(prettyBand(band), band, counts.get(band)));
  }
  markActiveBand();
}

function pickerBandChip(label, band, n) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "picker-band" + (band === null ? " picker-band-all" : "");
  b.dataset.band = band === null ? "" : band;
  if (band !== null) b.appendChild(makeBandIcon(band, "picker-band-icon"));
  const txt = document.createElement("span");
  txt.className = "picker-band-label";
  txt.textContent = `${label} (${n})`;
  b.appendChild(txt);
  b.addEventListener("click", () => { pickerBand = band; markActiveBand(); renderPickerSongs(); });
  return b;
}

function markActiveBand() {
  const key = pickerBand === null ? "" : pickerBand;
  [...pickerBandsEl.children].forEach((c) => c.classList.toggle("active", c.dataset.band === key));
}

function renderPickerSongs() {
  const q = pickerSearchEl.value.trim().toLowerCase();
  const list = allSongs.filter((s) => {
    if (pickerBand && s.band !== pickerBand) return false;
    if (!q) return true;
    return s.song.toLowerCase().includes(q)
      || prettyBand(s.band).toLowerCase().includes(q)
      || s.band.toLowerCase().includes(q);
  });
  pickerSongsEl.replaceChildren();
  if (!list.length) { pickerSongsEl.textContent = "일치하는 곡이 없어요."; return; }
  const CAP = 300; // 리스트 폭주 방지 — 넘으면 검색으로 좁히도록 유도
  for (const s of list.slice(0, CAP)) {
    const li = document.createElement("li");
    li.className = "picker-song";
    const info = elDiv("picker-song-info");
    const t = elDiv("picker-song-title"); t.textContent = s.song;
    const meta = elDiv("picker-song-band");
    meta.textContent = `${prettyBand(s.band)} · ${s.camelot} · 에너지 ${fmtNum(s.energy)}`;
    info.append(t, meta);
    const addBtn = document.createElement("button");
    addBtn.type = "button"; addBtn.className = "picker-add"; addBtn.textContent = "추가";
    addBtn.addEventListener("click", () => insertSong(s));
    li.append(makeBandIcon(s.band, "picker-song-icon"), info, addBtn);
    li.addEventListener("dblclick", () => insertSong(s));
    pickerSongsEl.appendChild(li);
  }
  if (list.length > CAP) {
    const more = document.createElement("li");
    more.className = "picker-more";
    more.textContent = `+${list.length - CAP}곡 더 있음 — 검색으로 좁혀 주세요`;
    pickerSongsEl.appendChild(more);
  }
}

function insertSong(song) {
  pushHistory();
  const at = Math.min(Math.max(insertAtIndex, 0), picks.length);
  picks.splice(at, 0, buildAddedPick(song));
  renderTracklist(picks);
  reconcilePlayer();
  syncGraphToEdited();
  closeSongPicker();
  track("song_added", { idx: song.idx });
}

// 추가곡을 세트리스트 pick 형태로 구성(엔진 pick과 렌더 호환). harmonic="added"로 배지 구분.
function buildAddedPick(song) {
  return {
    position: 0, idx: song.idx, video_id: song.video_id, band: song.band,
    song: song.song, camelot: song.camelot, energy: song.energy, stage_index: -1,
    reason: {
      stage_energy_target: 0, matched_energy: song.energy, harmonic: "added",
      prev_camelot: null, brightness_fit: 0, text: "직접 추가한 곡",
    },
  };
}

pickerSearchEl.addEventListener("input", renderPickerSongs);
// 백드롭/닫기(data-close)만 닫기 — 패널 내부 클릭은 유지.
pickerEl.addEventListener("click", (e) => {
  if (e.target instanceof HTMLElement && e.target.dataset && "close" in e.target.dataset) closeSongPicker();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !pickerEl.classList.contains("hidden")) closeSongPicker();
});

// ── UI 헬퍼 ───────────────────────────────────────────────────────────────────
$("next-btn").addEventListener("click", () => playSong(current + 1, false));
$("prev-btn").addEventListener("click", () => playSong(current - 1, false));

// 전체 세트리스트 공유(B2) — 'YouTube 재생목록' 버튼 → 공유 팝업(안내·URL 복사·유튜브 듣기).
// watch_videos 익명 링크라 OAuth 불필요하고 링크만 있으면 같은 곡·순서로 재생 가능.
// (제목·공개 설정된 계정 저장형은 OAuth+Data API 필요 — 백로그 B1.)
const shareModalEl = $("share-modal");
const shareUrlInputEl = $("share-url");
let shareUrl = "";

$("yt-playlist-btn").addEventListener("click", () => {
  if (!picks.length) return;
  const ids = picks.map((p) => p.video_id).join(",");
  shareUrl = `https://www.youtube.com/watch_videos?video_ids=${ids}`;
  shareUrlInputEl.value = shareUrl;
  resetCopyBtn();
  show(shareModalEl);
  lockBodyScroll(true);
  track("playlist_shared", { count: picks.length });
});

$("share-open").addEventListener("click", () => {
  if (shareUrl) window.open(shareUrl, "_blank", "noopener");
});
$("share-copy").addEventListener("click", copyShareUrl);
shareModalEl.addEventListener("click", (e) => {
  if (e.target instanceof HTMLElement && e.target.dataset && "close" in e.target.dataset) closeShareModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !shareModalEl.classList.contains("hidden")) closeShareModal();
});

function closeShareModal() { hide(shareModalEl); lockBodyScroll(false); }
function resetCopyBtn() {
  const btn = $("share-copy");
  btn.textContent = "복사";
  btn.classList.remove("copied");
}

async function copyShareUrl() {
  const btn = $("share-copy");
  let ok = false;
  try {
    await navigator.clipboard.writeText(shareUrl);
    ok = true;
  } catch (_) {
    // 폴백: input 선택 후 execCommand(구형·클립보드 차단 환경).
    shareUrlInputEl.focus();
    shareUrlInputEl.select();
    try { ok = document.execCommand("copy"); } catch (_2) { ok = false; }
  }
  btn.textContent = ok ? "복사됨 ✓" : "직접 복사하세요";
  btn.classList.toggle("copied", ok);
  setTimeout(resetCopyBtn, 1500);
  if (ok) track("playlist_link_copied", { count: picks.length });
}

// 이번 요청에 실제 적용된 밴드(수동선택 ∪ 프롬프트 자동감지)를 체크박스에 시각 반영한다.
// manualBands는 건드리지 않는다(자동감지분이 다음 요청에 지속되지 않도록). 프로그램적 .checked
// 대입이므로 change 이벤트가 발생하지 않아 manualBands가 오염되지 않는다.
function syncBandChecks(bands) {
  const applied = new Set(bands || []);
  document.querySelectorAll(".band-cb").forEach((cb) => {
    cb.checked = manualBands.has(cb.value) || applied.has(cb.value);
  });
}

function highlight(index) {
  [...tracklistEl.children].forEach((li, i) => li.classList.toggle("active", i === index));
  const active = tracklistEl.children[index];
  if (active) active.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function updateNowPlaying(p) {
  nowPlayingEl.replaceChildren();
  const strong = document.createElement("span");
  strong.textContent = `▶ ${p.song} `;
  const band = document.createElement("span");
  band.className = "np-band";
  band.textContent = `— ${prettyBand(p.band)} `;
  const link = document.createElement("a");
  link.className = "np-link";
  link.href = `https://youtu.be/${p.video_id}`;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "YouTube에서 열기 ↗";
  nowPlayingEl.append(strong, band, link);
}

function prettyBand(band) {
  return String(band).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function harmonicLabelKo(h) {
  return { seed: "시작곡", same: "동일조성", adjacent: "하모닉인접", non_harmonic: "조성전환", added: "추가한 곡" }[h] || h;
}
function fmtNum(v) { return (typeof v === "number" ? v : 0).toFixed(2); }
function fmtSigned(v) { const n = typeof v === "number" ? v : 0; return (n >= 0 ? "+" : "") + n.toFixed(2); }

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function toggle(el, on) { el.classList.toggle("hidden", !on); }
