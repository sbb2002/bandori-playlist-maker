// 이번 요청에 실제 적용된 밴드(수동선택 ∪ 프롬프트 자동감지)를 체크박스에 시각 반영한다.
// manualBands는 건드리지 않는다(자동감지분이 다음 요청에 지속되지 않도록). 프로그램적 .checked
// 대입이므로 change 이벤트가 발생하지 않아 manualBands가 오염되지 않는다.
function syncBandChecks(bands) {
  const applied = new Set(bands || []);
  document.querySelectorAll(".band-cb").forEach((cb) => {
    cb.checked = manualBands.has(cb.value) || applied.has(cb.value);
  });
}

// autoAdvance=true(자동 다음곡 전환)일 때만 followTracklist 게이트를 적용한다.
// 수동 조작(트랙 클릭·이전/다음 버튼·편집 후 재정합)은 인자를 생략해 항상 스크롤.
function highlight(index, autoAdvance) {
  [...tracklistEl.children].forEach((li, i) => li.classList.toggle("active", i === index));
  wheelNodeEls.forEach((g, i) => g.classList.toggle("active", i === index));
  updateWheelEdgeOpacity(index);
  const active = tracklistEl.children[index];
  if (!active) return;
  if (autoAdvance && !followTracklist) return;
  // 자동 다음곡 "따라가기"는 이동 거리가 짧으면 nearest가 거의 움직이지 않아 순간이동처럼
  // 보인다. center로 항상 뚜렷하게 움직이게 한다. 수동 조작(트랙 클릭 등)은 사용자가 이미
  // 보던 위치를 존중해 최소한만 보정하는 nearest 그대로 둔다.
  const block = autoAdvance ? "center" : "nearest";
  active.scrollIntoView({ block, behavior: "smooth" });
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
  link.textContent = t("player.openYoutube");
  nowPlayingEl.append(strong, band, link);
  updatePlaybarInfo(p);
}

// ── 하단 고정 플레이바 (사용자 제안 2026-07-13) ─────────────────────────────────
// 트랙리스트를 스크롤 중에도 현재 곡 정보·진행률·재생 조작이 가능한 상시 노출 바.
// 플레이리스트 생성 전엔 숨겨져 있다가(transform: translateY(100%)), 생성 시 아래에서 올라온다.
const playbarEl = $("playbar");
const playbarProgressEl = $("playbar-progress");
const playbarProgressFillEl = $("playbar-progress-fill");
const playbarTitleEl = $("playbar-title");
const playbarTitleTrackEl = $("playbar-title-track");
const playbarTitleTextEl = $("playbar-title-text");
const playbarBandEl = $("playbar-band");
const playbarTimeEl = $("playbar-time");
const playbarCountEl = $("playbar-count");
const playbarPlayBtn = $("playbar-play");
const playbarRepeatBtn = $("playbar-repeat");
// "off" → "one"(현재 곡만 반복) → "all"(끝까지 가면 처음부터) → "off" 순환.
const REPEAT_MODES = ["off", "one", "all"];
let repeatMode = "off";
let playbarProgressTimer = null;

// 재생/일시정지 아이콘 — 나머지 컨트롤과 동일한 currentColor 인라인 SVG(이모지 혼용 방지).
const ICON_PLAY =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
  '<path d="M8 5.6c0-.8.9-1.3 1.6-.8l9 6.4c.6.4.6 1.3 0 1.7l-9 6.4c-.7.4-1.6 0-1.6-.9V5.6z"/></svg>';
const ICON_PAUSE =
  '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
  '<rect x="6.6" y="5" width="4" height="14" rx="1.3"/><rect x="13.4" y="5" width="4" height="14" rx="1.3"/></svg>';

function showPlaybar() { playbarEl.classList.add("show"); }
function hidePlaybar() { playbarEl.classList.remove("show"); stopPlaybarProgressTimer(); }

function updatePlaybarInfo(p) {
  playbarTitleTextEl.textContent = p.song;
  playbarBandEl.textContent = prettyBand(p.band);

  // 현재곡/전체곡 — 현재 번호만 강조(흰색·큰 글자), 구분자·전체는 흐리게.
  playbarCountEl.replaceChildren();
  const cur = document.createElement("span");
  cur.className = "playbar-count-cur";
  cur.textContent = String(current + 1);
  const sep = document.createElement("span");
  sep.className = "playbar-count-sep";
  sep.textContent = "/";
  const total = document.createElement("span");
  total.className = "playbar-count-total";
  total.textContent = String(picks.length);
  playbarCountEl.append(cur, sep, total);

  updatePlaybarProgressUI(0, 0); // 곡 전환 시 진행률 리셋, 다음 PLAYING/타이머가 실측치로 갱신
  updateTitleMarquee();
}

// 곡 이름이 바 폭을 넘칠 때만 마퀴를 켠다. 사본을 하나 덧붙여 [원본][간격][사본]으로 만들고,
// 한 벌 길이(글자폭+간격)만큼 왼쪽으로 밀면 사본이 원본 자리에 정확히 겹쳐 무한 루프로 이어진다.
// 속도는 이동 거리에 비례(≈45px/s)해 길이와 무관하게 체감 속도를 일정하게 유지한다.
const MARQUEE_GAP_PX = 44;
const MARQUEE_SPEED_PX_PER_SEC = 45;

function updateTitleMarquee() {
  playbarTitleEl.classList.remove("marquee");
  playbarTitleEl.style.removeProperty("--marquee-distance");
  playbarTitleEl.style.removeProperty("--marquee-duration");
  const oldClone = playbarTitleTrackEl.querySelector(".playbar-title-clone");
  if (oldClone) oldClone.remove();

  // 클래스·텍스트·사본 제거가 레이아웃에 반영된 뒤라야 순수 글자폭을 잴 수 있다(다음 프레임).
  requestAnimationFrame(() => {
    const textWidth = playbarTitleTextEl.scrollWidth;
    if (textWidth - playbarTitleEl.clientWidth <= 2) return; // 안 넘치면 말줄임 유지

    const clone = document.createElement("span");
    clone.className = "playbar-title-text playbar-title-clone";
    clone.setAttribute("aria-hidden", "true"); // 스크린리더에 곡명이 두 번 읽히지 않도록
    clone.textContent = playbarTitleTextEl.textContent;
    playbarTitleTrackEl.appendChild(clone);

    const distance = textWidth + MARQUEE_GAP_PX;
    playbarTitleEl.style.setProperty("--marquee-distance", `${distance}px`);
    playbarTitleEl.style.setProperty("--marquee-gap", `${MARQUEE_GAP_PX}px`);
    playbarTitleEl.style.setProperty("--marquee-duration", `${(distance / MARQUEE_SPEED_PX_PER_SEC).toFixed(1)}s`);
    playbarTitleEl.classList.add("marquee");
  });
}
// 화면 폭이 바뀌면 넘침 여부가 달라지므로 다시 잰다(회전·창 크기 변경).
window.addEventListener("resize", () => {
  if (playbarEl.classList.contains("show")) updateTitleMarquee();
});

function setPlaybarPlaying(isPlaying) {
  playbarPlayBtn.innerHTML = isPlaying ? ICON_PAUSE : ICON_PLAY;
  const playLabel = isPlaying ? t("player.pause") : t("player.play");
  playbarPlayBtn.setAttribute("aria-label", playLabel);
  playbarPlayBtn.title = playLabel;
  playWaveEngine.playing = isPlaying;
}

// ── 재생 버튼 어쿠스틱 웨이브 링 ──────────────────────────────────────────────
// 사인파로 바깥 반지름을 변조한 "링(도넛)" 경로를 절차적으로 생성(핸드코딩 path data 아님).
// 바깥 경계는 물결(outerBase + amp*sin), 안쪽 경계는 원(innerR) — evenodd로 사이 띠만 채운다.
function playWaveRingPath(cx, cy, innerR, outerBase, amp, lobes, points) {
  const outer = [];
  const inner = [];
  for (let i = 0; i <= points; i++) {
    const t = (i / points) * Math.PI * 2;
    const rad = outerBase + amp * Math.sin(lobes * t);
    outer.push([cx + rad * Math.cos(t), cy + rad * Math.sin(t)]);
    inner.push([cx + innerR * Math.cos(t), cy + innerR * Math.sin(t)]);
  }
  const ring = (pts) => pts.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(2) + "," + p[1].toFixed(2)).join(" ") + " Z";
  return ring(outer) + " " + ring(inner);
}

const playWaveA = $("play-wave-a");
const playWaveB = $("play-wave-b");
playWaveA.setAttribute("fill-rule", "evenodd");
playWaveB.setAttribute("fill-rule", "evenodd");
const playWaveFlowAEl = document.getElementById("playWaveFlowA");
const playWaveFlowBEl = document.getElementById("playWaveFlowB");

// 재생↔일시정지 전환 시 회전 속도·색 흐름 속도·링 크기가 모두 같은 "가속/감속 곡선"을 따라
// 서서히 목표치로 수렴한다(지수 감쇠). 일시정지의 목표는 속도 0·크기 0(=버튼 테두리 반지름까지
// 줄어들어 소멸)이라, 감속될수록 링이 자연스럽게 원(버튼) 쪽으로 오그라들며 사라진다.
const PLAY_WAVE_COLLAPSE_R = 27; // 완전히 오그라들었을 때 반지름 = 버튼 테두리
const PLAY_WAVE_REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const PLAY_WAVE_RATE = PLAY_WAVE_REDUCED_MOTION ? 40 : 2.4; // reduced-motion이면 사실상 즉시 스냅
const playWaveEngine = {
  playing: false,
  a: { innerFull: 27, outerFull: 34, ampFull: 3.2, lobes: 4, rotFull: 360 / 16, flowFull: 64 / 10, flowPeriod: 64,
       angle: 0, vel: 0, extent: 0, flowOff: 0, flowVel: 0, el: playWaveA, gradEl: playWaveFlowAEl },
  b: { innerFull: 30, outerFull: 35, ampFull: 2.4, lobes: 3, rotFull: -360 / 40, flowFull: -84 / 14, flowPeriod: 84,
       angle: 0, vel: 0, extent: 0, flowOff: 0, flowVel: 0, el: playWaveB, gradEl: playWaveFlowBEl },
};
function playWaveLerp(a, b, t) { return a + (b - a) * t; }
function stepPlayWave(w, dt) {
  const targetVel = playWaveEngine.playing ? w.rotFull : 0;
  const targetExtent = playWaveEngine.playing ? 1 : 0;
  const targetFlowVel = playWaveEngine.playing ? w.flowFull : 0;
  const f = 1 - Math.exp(-PLAY_WAVE_RATE * dt);
  w.vel += (targetVel - w.vel) * f;
  w.extent += (targetExtent - w.extent) * f;
  w.flowVel += (targetFlowVel - w.flowVel) * f;
  w.angle = (w.angle + w.vel * dt) % 360;
  w.flowOff = (w.flowOff + w.flowVel * dt) % w.flowPeriod;

  const innerR = playWaveLerp(PLAY_WAVE_COLLAPSE_R, w.innerFull, w.extent);
  const outerBase = playWaveLerp(PLAY_WAVE_COLLAPSE_R, w.outerFull, w.extent);
  const amp = w.ampFull * w.extent;
  w.el.setAttribute("d", playWaveRingPath(50, 50, innerR, outerBase, amp, w.lobes, 90));
  w.el.style.transform = "rotate(" + w.angle.toFixed(2) + "deg)";
  w.el.style.opacity = w.extent.toFixed(3);
  w.gradEl.setAttribute("gradientTransform", "translate(" + w.flowOff.toFixed(2) + " 0)");
}
let playWaveLastT = null;
function playWaveFrame(t) {
  if (playWaveLastT == null) playWaveLastT = t;
  const dt = Math.min((t - playWaveLastT) / 1000, 0.05);
  playWaveLastT = t;
  stepPlayWave(playWaveEngine.a, dt);
  stepPlayWave(playWaveEngine.b, dt);
  requestAnimationFrame(playWaveFrame);
}
requestAnimationFrame(playWaveFrame);

function startPlaybarProgressTimer() {
  stopPlaybarProgressTimer();
  updatePlaybarProgressFromPlayer();
  playbarProgressTimer = setInterval(updatePlaybarProgressFromPlayer, 1000);
}
function stopPlaybarProgressTimer() {
  if (playbarProgressTimer) { clearInterval(playbarProgressTimer); playbarProgressTimer = null; }
}
function updatePlaybarProgressFromPlayer() {
  if (!player || typeof player.getCurrentTime !== "function") return;
  updatePlaybarProgressUI(player.getCurrentTime() || 0, player.getDuration() || 0);
}
function updatePlaybarProgressUI(cur, dur) {
  const pct = dur > 0 ? clamp((cur / dur) * 100, 0, 100) : 0;
  playbarProgressFillEl.style.width = `${pct}%`;
  playbarProgressEl.setAttribute("aria-valuenow", String(Math.round(pct)));
  playbarTimeEl.textContent = `${fmtTime(cur)} / ${fmtTime(dur)}`;
}
function fmtTime(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// 진행바 클릭·드래그 = seek(player.seekTo). duration 미확보(로딩 중 등) 시 무시.
function seekToFraction(fx) {
  if (!player || typeof player.getDuration !== "function") return;
  const dur = player.getDuration() || 0;
  if (dur <= 0) return;
  player.seekTo(dur * fx, true);
  updatePlaybarProgressUI(dur * fx, dur);
}
(function bindPlaybarSeek() {
  let dragging = false;
  const seekAt = (clientX) => {
    const r = playbarProgressEl.getBoundingClientRect();
    seekToFraction(clamp01((clientX - r.left) / r.width));
  };
  playbarProgressEl.addEventListener("pointerdown", (e) => {
    dragging = true;
    playbarProgressEl.classList.add("dragging"); // 드래그 중엔 굵은 선·손잡이 유지(터치 포함)
    playbarProgressEl.setPointerCapture(e.pointerId);
    seekAt(e.clientX);
  });
  playbarProgressEl.addEventListener("pointermove", (e) => { if (dragging) seekAt(e.clientX); });
  const endDrag = (e) => {
    if (!dragging) return;
    dragging = false;
    playbarProgressEl.classList.remove("dragging");
    try { playbarProgressEl.releasePointerCapture(e.pointerId); } catch (_) {/* 이미 해제됨 */}
  };
  playbarProgressEl.addEventListener("pointerup", endDrag);
  playbarProgressEl.addEventListener("pointercancel", endDrag);
})();

$("playbar-prev").addEventListener("click", () => playSong(current - 1, false));
$("playbar-next").addEventListener("click", () => playSong(current + 1, false));
playbarPlayBtn.addEventListener("click", () => {
  if (!player || typeof player.getPlayerState !== "function") return;
  if (player.getPlayerState() === YT.PlayerState.PLAYING) player.pauseVideo();
  else player.playVideo();
});
playbarRepeatBtn.addEventListener("click", () => {
  repeatMode = REPEAT_MODES[(REPEAT_MODES.indexOf(repeatMode) + 1) % REPEAT_MODES.length];
  applyRepeatButtonState();
});
// 배지 글자(data-repeat-label)·aria-label(다음 클릭 시 어떻게 되는지)·title(현재 상태)을
// repeatMode에 맞춰 반영. off일 땐 .active가 빠지므로 CSS ::after 배지 자체가 안 보인다.
function applyRepeatButtonState() {
  const active = repeatMode !== "off";
  playbarRepeatBtn.classList.toggle("active", active);
  playbarRepeatBtn.setAttribute("aria-pressed", active ? "true" : "false");
  if (repeatMode === "off") {
    playbarRepeatBtn.dataset.repeatLabel = "";
    playbarRepeatBtn.setAttribute("aria-label", t("playbar.repeatOffAria"));
    playbarRepeatBtn.title = t("playbar.repeatOffTitle");
  } else if (repeatMode === "one") {
    playbarRepeatBtn.dataset.repeatLabel = "1";
    playbarRepeatBtn.setAttribute("aria-label", t("playbar.repeatOneAria"));
    playbarRepeatBtn.title = t("playbar.repeatOneTitle");
  } else {
    playbarRepeatBtn.dataset.repeatLabel = "A";
    playbarRepeatBtn.setAttribute("aria-label", t("playbar.repeatAllAria"));
    playbarRepeatBtn.title = t("playbar.repeatAllTitle");
  }
}
// 뷰포트 중심과 엘리먼트 중심 사이의 거리(px). 값이 작을수록 "지금 그 엘리먼트를 보고 있다"에 가깝다.
function getViewportCenterDistance(el) {
  const rect = el.getBoundingClientRect();
  const elCenter = rect.top + rect.height / 2;
  const viewportCenter = window.innerHeight / 2;
  return Math.abs(elCenter - viewportCenter);
}

// 곡 정보 클릭 → 플레이어 카드 / 트랙리스트 현재 곡 중 "지금 보고 있지 않은 쪽"으로 스크롤.
// 토글 변수 없이 매번 실제 스크롤 위치(뷰포트 중심과의 거리)를 기준으로 판단한다:
// 두 후보 중 더 가까운(=지금 보고 있는) 쪽이 아닌 다른 쪽으로 이동. 어느 쪽도 뚜렷이
// "보고 있지 않은" 애매한 위치라도 이 규칙을 그대로 적용하면 둘 중 가까운 쪽으로 자연스럽게 붙는다.
$("playbar-info").addEventListener("click", () => {
  const playerEl = document.querySelector(".player-card");
  const trackEl = current >= 0 ? tracklistEl.children[current] : null;

  if (playerEl && trackEl) {
    const target =
      getViewportCenterDistance(playerEl) <= getViewportCenterDistance(trackEl) ? trackEl : playerEl;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    // 트랙리스트 쪽으로 이동했다면 "따라가기" 켬. 플레이어 쪽으로 이동했다면(=영상을
    // 보러 감) 꺼서, 다음 곡 자동 전환 때 화면을 다시 끌어오지 않는다.
    followTracklist = target === trackEl;
  } else if (playerEl) {
    playerEl.scrollIntoView({ behavior: "smooth", block: "center" });
    followTracklist = false;
  }
});

// 사용자가 직접 화면을 움직이면(휠·터치 스크롤) "따라가기"를 끈다. scrollIntoView 같은
// 프로그램적 스크롤은 wheel/touchmove를 발생시키지 않으므로 오작동하지 않는다.
window.addEventListener("wheel", () => { followTracklist = false; }, { passive: true });
window.addEventListener("touchmove", () => { followTracklist = false; }, { passive: true });

// 유튜브 iframe에 포커스가 가면(=영상을 보고/조작하고 있음) "따라가기"를 끈다.
document.addEventListener("focusin", (e) => {
  if (e.target instanceof HTMLIFrameElement) followTracklist = false;
});

// prettyBand/keyLabel/CAMELOT_TO_KEY_LABEL/PICK_PARAM_DEFS/makeParamBadge/harmonicLabelKo/
// harmonicTooltipKo/fmtNum/fmtSigned/show/hide/toggle은 app/utils.js 참조.

// 언어 전환 시 플레이바의 동적 title/aria-label(재생·반복 버튼)을 새 언어로 다시 반영.
document.addEventListener("i18n:change", () => {
  setPlaybarPlaying(playWaveEngine.playing);
  applyRepeatButtonState();
});
