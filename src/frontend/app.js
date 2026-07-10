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
const customToggle = $("custom-stages-toggle");

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
    const span = document.createElement("span");
    span.textContent = `${prettyBand(b.band)} (${b.count})`;
    label.append(cb, span);
    bandListEl.appendChild(label);
  }
}

function collectBands() {
  return [...document.querySelectorAll(".band-cb:checked")].map((c) => c.value);
}

$("band-clear").addEventListener("click", () => {
  document.querySelectorAll(".band-cb:checked").forEach((c) => (c.checked = false));
});

customToggle.addEventListener("change", () => {
  toggle(stageEditorEl, customToggle.checked);
  if (customToggle.checked) renderStageEditor();
});
$("stage-count").addEventListener("input", () => {
  if (customToggle.checked) renderStageEditor();
});

function renderStageEditor() {
  const n = Math.max(2, Math.min(5, parseInt($("stage-count").value, 10) || 3));
  const totalMin = Math.max(10, Math.min(180, parseInt($("target-minutes").value, 10) || 60));
  const perMin = Math.max(1, Math.round(totalMin / n));
  stageEditorEl.replaceChildren();
  for (let i = 0; i < n; i++) {
    const energy = +(0.3 + (0.55 * i) / (n - 1)).toFixed(2); // 기본 0.30→0.85 상승 아크
    const row = document.createElement("div");
    row.className = "stage-row";

    const head = document.createElement("div");
    head.className = "stage-row-head";
    head.textContent = `${i + 1}단계`;

    const eVal = document.createElement("span");
    eVal.className = "stage-eval";
    eVal.textContent = energy.toFixed(2);
    const slider = document.createElement("input");
    slider.type = "range"; slider.min = "0"; slider.max = "1"; slider.step = "0.05";
    slider.value = String(energy);
    slider.className = "stage-energy";
    slider.addEventListener("input", () => (eVal.textContent = (+slider.value).toFixed(2)));

    const eWrap = document.createElement("div");
    eWrap.className = "stage-ctrl";
    const eLbl = document.createElement("span"); eLbl.className = "stage-lbl"; eLbl.textContent = "에너지";
    eWrap.append(eLbl, slider, eVal);

    const mInput = document.createElement("input");
    mInput.type = "number"; mInput.min = "1"; mInput.max = "180";
    mInput.value = String(perMin);
    mInput.className = "stage-minutes";
    const mWrap = document.createElement("div");
    mWrap.className = "stage-ctrl";
    const mLbl = document.createElement("span"); mLbl.className = "stage-lbl"; mLbl.textContent = "분";
    mWrap.append(mLbl, mInput);

    row.append(head, eWrap, mWrap);
    stageEditorEl.appendChild(row);
  }
}

function collectStages() {
  if (!customToggle.checked) return null;
  const rows = [...stageEditorEl.querySelectorAll(".stage-row")];
  if (!rows.length) return null;
  return rows.map((r) => ({
    energy: +r.querySelector(".stage-energy").value,
    minutes: Math.max(1, parseInt(r.querySelector(".stage-minutes").value, 10) || 5),
  }));
}

loadBands();

// ── 렌더 ─────────────────────────────────────────────────────────────────────
function renderResult(data) {
  picks = data.picks || [];
  estimatedTotal = data.estimated_total_seconds || 0;
  playedSeconds = 0;
  halfFired = false;
  current = -1;

  if (!picks.length) {
    showError("조건에 맞는 곡을 찾지 못했어요. 요청을 조금 바꿔 보세요.");
    return;
  }

  renderSummary(data);
  renderTracklist(picks);
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
    li.append(pos, bodyEl);
    tracklistEl.appendChild(li);
  });
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
  highlight(0);
  updateNowPlaying(picks[0]);

  const boot = () => {
    if (player && player.loadVideoById) {
      player.loadVideoById(picks[0].video_id);
      return;
    }
    player = new YT.Player("player", {
      videoId: picks[0].video_id,
      playerVars: { autoplay: 1, playsinline: 1, rel: 0 },
      events: {
        onReady: (e) => e.target.playVideo(),
        onStateChange: onPlayerStateChange,
      },
    });
  };

  if (ytReady) boot();
  else { pendingStart = boot; loadYouTubeApi(); }
}

function onPlayerStateChange(e) {
  if (e.data === YT.PlayerState.ENDED) {
    playedSeconds += safeDuration();
    maybeFireHalf();
    if (current + 1 < picks.length) playSong(current + 1, true);
  }
}

function playSong(index, auto) {
  if (index < 0 || index >= picks.length) return;
  current = index;
  const p = picks[index];
  highlight(index);
  updateNowPlaying(p);
  if (player && player.loadVideoById) player.loadVideoById(p.video_id);
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

// ── UI 헬퍼 ───────────────────────────────────────────────────────────────────
$("next-btn").addEventListener("click", () => playSong(current + 1, false));
$("prev-btn").addEventListener("click", () => playSong(current - 1, false));

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
  band.textContent = `— ${prettyBand(p.band)}`;
  nowPlayingEl.append(strong, band);
}

function prettyBand(band) {
  return String(band).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function harmonicLabelKo(h) {
  return { seed: "시작곡", same: "동일조성", adjacent: "하모닉인접", non_harmonic: "조성전환" }[h] || h;
}
function fmtNum(v) { return (typeof v === "number" ? v : 0).toFixed(2); }
function fmtSigned(v) { const n = typeof v === "number" ? v : 0; return (n >= 0 ? "+" : "") + n.toFixed(2); }

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function toggle(el, on) { el.classList.toggle("hidden", !on); }
