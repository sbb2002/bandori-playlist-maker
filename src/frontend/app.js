/* setlist-maker 프론트 — 요청 → 세트리스트 렌더 → YouTube 순차 자동재생 + umami 계측.
 * 백엔드 계약: architecture.md 스키마3 (POST /api/setlist, GET /api/health, 공통 에러 포맷).
 */
"use strict";

const API_BASE = (window.SETLIST_API_BASE || "http://localhost:8000").replace(/\/$/, "");
const AVG_SONG_SECONDS = 213; // duration 미확보 시 폴백(백엔드와 동일 가정).

// ALL/Original/Cover 필터 알약 — bandori-song-sorter의 티어 필터 알약(06-filter-pills.js) 참고.
// 곡 추가 팝업(picker-type-filter)과 세부 설정(settings-type-filter) 양쪽에서 공유.
const PICKER_TYPE_OPTIONS = [
  { key: "all", label: "ALL" },
  { key: "original", label: "Original" },
  { key: "cover", label: "Cover" },
];

// ── DOM ──────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const form = $("request-form");
const submitBtn = $("submit-btn");
const loadingEl = $("loading");
const errorEl = $("error");
const promptEl = $("prompt");
const promptHintEl = $("prompt-hint");
const omakaseBtn = $("omakase-btn");
const minutesEl = $("target-minutes");
const minutesHintEl = $("target-minutes-hint");
const resultEl = $("result");
const summaryEl = $("summary");
const tracklistEl = $("tracklist");
const nowPlayingEl = $("now-playing");
const wheelSvgEl = $("camelot-wheel");
const wheelModeToggleEl = $("wheel-mode-toggle");

// ── 테마(라이트/다크) ────────────────────────────────────────────────────────────
// index.html head의 인라인 스크립트가 렌더 전에 이미 data-theme을 세팅해뒀으므로
// 여기서는 토글 버튼 클릭 시 상태 반전 + localStorage 저장만 담당(FOUC 방지는 그쪽 담당).
const themeToggleBtn = $("theme-toggle");
if (themeToggleBtn) {
  themeToggleBtn.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
    themeToggleBtn.setAttribute("aria-pressed", String(next === "dark"));
    track("theme_toggle", { theme: next });
  });
  themeToggleBtn.setAttribute("aria-pressed", String(document.documentElement.dataset.theme === "dark"));
}

// ── 재생 상태 ─────────────────────────────────────────────────────────────────
let picks = [];
let current = -1;
let estimatedTotal = 0;
let playedSeconds = 0;
let halfFired = false;
let errorSkips = 0; // 재생불가 영상 연속 스킵 가드(무한 루프 방지)
// 플레이바 곡 이름(#playbar-info) 클릭 → 트랙리스트 쪽으로 스크롤했고, 그 뒤로 사용자가
// 화면을 직접 움직이거나 유튜브 영상에 포커스를 두지 않았다면 true. true인 동안에만
// 다음 곡 자동 전환 시 화면이 그 곡 위치로 따라간다(수동 클릭/이전·다음 버튼은 원래도
// 항상 스크롤되므로 이 플래그의 영향을 받지 않음 — highlight()의 autoAdvance 인자 참고).
let followTracklist = false;
let loadedVideoId = null; // 플레이어에 로드/큐된 영상 id — 편집 후 재생 정합에 사용
let playbackStarted = false; // 첫 PLAYING 이후 true — 편집 시 cue(정지) vs load(자동재생) 선택
// 통합 되돌리기 스택(Ctrl+Z): {kind:'edit', picks, current} | {kind:'preset-delete', preset, index}.
// 'edit'은 새 플레이리스트 생성 시 리셋, 'preset-delete'는 유지.
const undoStack = [];

// ── 모드 상태 ─────────────────────────────────────────────────────────────────
let currentMode = "ai"; // "ai" | "custom"
// 프리셋 자동저장용 최신 스냅샷(renderResult에서 갱신). lastStages는 커스텀 모드의 기본값용.
let lastParams = {};
let lastAppliedBands = [];
let lastStages = [];
let currentPresetId = null; // 현재 세션이 매핑된 프리셋 id(편집 시 이 프리셋 갱신)
let restoring = false; // 프리셋 복원 중엔 새 프리셋 자동생성 생략
// DEPRECATED(2026-08-11): previousPrompt(직전 성공 요청 저장)는 제거됨 — AI/커스텀 모드가
// 완전히 분리된 뒤 백엔드가 same_as_previous 판정 결과를 라우팅에 쓰지 않아(honor는 모드로만
// 결정) 더 이상 보낼 이유가 없다. src/backend/app/adapters/prompt.py의 동일 코멘트 참조.

// ── umami 계측(스크립트 미설치 시 무해) ─────────────────────────────────────────
function track(name, data) {
  try {
    if (window.umami && typeof window.umami.track === "function") window.umami.track(name, data);
  } catch (_) {/* 계측 실패는 UX에 영향 주지 않음 */}
}

// 백엔드도 500자 하드캡을 두지만(schemas.py), 여기서는 프론트에서 먼저 입력을 막고
// 한계에 닿았을 때만 안내한다(native maxlength라 501번째 글자부터는 조용히 씹혀서 이유를 알기 어려움).
promptEl.addEventListener("input", () => {
  if (promptEl.value.length >= promptEl.maxLength) {
    promptHintEl.textContent = `⚠️ ${promptEl.maxLength}자까지만 적을 수 있어요.`;
    promptHintEl.classList.add("notice");
  } else {
    promptHintEl.textContent = "";
    promptHintEl.classList.remove("notice");
  }
});

// ── 오마카세(시간대+날씨 기반 프롬프트 자동 생성) ──────────────────────────────────
const OMAKASE_TIME_PHRASES = {
  dawn: ["차분하게 하루를 여는", "고요한 새벽 감성의"],
  morning: ["상쾌하게 하루를 시작하는", "기운 넘치는 아침"],
  afternoon: ["나른한 오후를 깨워줄", "집중력 올려주는"],
  evening: ["노을 지는 저녁에 어울리는", "하루를 마무리하는 잔잔한"],
  night: ["늦은 밤 감성적인", "잠들기 전 편안한"],
};
const OMAKASE_WEATHER_PHRASES = {
  clear: ["맑고 청량한", "햇살 좋은 날씨에 어울리는"],
  cloudy: ["흐린 날씨에 잔잔한", "구름 낀 하늘 아래 아련한"],
  rain: ["비 오는 날 감성적인", "빗소리와 잘 어울리는"],
  snow: ["눈 내리는 날의 포근한", "하얗게 눈 쌓인 겨울 감성의"],
  storm: ["천둥번개 치는 날 몰입감 있는", "폭풍우 속 강렬한"],
};
const OMAKASE_SUFFIXES = ["플레이리스트 만들어줘", "세트리스트 부탁해", "플리 하나 뽑아줘"];

function omakaseTimeOfDay(hour) {
  if (hour >= 5 && hour < 8) return "dawn";
  if (hour >= 8 && hour < 11) return "morning";
  if (hour >= 11 && hour < 17) return "afternoon";
  if (hour >= 17 && hour < 21) return "evening";
  return "night";
}

function omakaseWeatherCategory(code) {
  if (code === 0) return "clear";
  if (code <= 3 || code === 45 || code === 48) return "cloudy";
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return "rain";
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "snow";
  if (code >= 95) return "storm";
  return null;
}

const pickRandom = (arr) => arr[Math.floor(Math.random() * arr.length)];

// 날씨 API 남용 방지: localStorage에 10분 TTL로 캐시(같은 세션 반복 클릭은 물론
// 새로고침·재방문에도 재사용 — 위치는 10분 내엔 크게 안 변한다고 가정).
const OMAKASE_CACHE_KEY = "omakaseWeatherCache";
const OMAKASE_CACHE_TTL_MS = 10 * 60 * 1000;

function readOmakaseWeatherCache() {
  try {
    const cached = JSON.parse(localStorage.getItem(OMAKASE_CACHE_KEY));
    if (!cached || Date.now() - cached.ts > OMAKASE_CACHE_TTL_MS) return undefined;
    return cached.weather; // null도 유효 캐시(날씨 조회 실패를 기억해 재시도 안 함)
  } catch (_) {
    return undefined;
  }
}

function writeOmakaseWeatherCache(weather) {
  try {
    localStorage.setItem(OMAKASE_CACHE_KEY, JSON.stringify({ ts: Date.now(), weather }));
  } catch (_) {/* localStorage 불가 시 캐시 생략 — 매번 새로 조회될 뿐 기능엔 영향 없음 */}
}

// ponytail: 인메모리 프라미스 캐시 — 같은 페이지 안에서 오마카세를 연타해도 진행 중인
// fetch 하나만 기다리게 한다(중복 요청 방지). TTL은 위 localStorage 캐시가 담당.
let omakaseCtxPromise = null;
function getOmakaseContext() {
  if (!omakaseCtxPromise) {
    omakaseCtxPromise = (async () => {
      const ctx = { timeOfDay: omakaseTimeOfDay(new Date().getHours()), weather: null };
      const cachedWeather = readOmakaseWeatherCache();
      if (cachedWeather !== undefined) {
        ctx.weather = cachedWeather;
        return ctx;
      }
      if (!navigator.geolocation) return ctx;
      try {
        const pos = await new Promise((resolve, reject) =>
          navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 4000 })
        );
        const res = await fetch(
          `https://api.open-meteo.com/v1/forecast?latitude=${pos.coords.latitude}&longitude=${pos.coords.longitude}&current=weather_code`
        );
        const data = await res.json();
        ctx.weather = omakaseWeatherCategory(data.current?.weather_code);
      } catch (_) {/* 위치/날씨 조회 실패 시 시간대만으로 폴백 */}
      writeOmakaseWeatherCache(ctx.weather);
      return ctx;
    })();
  }
  return omakaseCtxPromise;
}

function buildOmakasePrompt(ctx) {
  const parts = [];
  if (ctx.weather && OMAKASE_WEATHER_PHRASES[ctx.weather]) {
    parts.push(pickRandom(OMAKASE_WEATHER_PHRASES[ctx.weather]));
  }
  parts.push(pickRandom(OMAKASE_TIME_PHRASES[ctx.timeOfDay]));
  parts.push(pickRandom(OMAKASE_SUFFIXES));
  return parts.join(" ");
}

const OMAKASE_COOLDOWN_MS = 5000; // 연타 방지 — 클릭 시점부터 최소 5초는 버튼 비활성 유지

if (omakaseBtn) {
  omakaseBtn.addEventListener("animationend", () => omakaseBtn.classList.remove("rolling"));
  omakaseBtn.addEventListener("click", async () => {
    track("omakase_click");
    const clickedAt = Date.now();
    omakaseBtn.disabled = true;
    omakaseBtn.classList.remove("rolling");
    void omakaseBtn.offsetWidth; // 연타 시에도 애니메이션이 재시작되도록 리플로우 강제
    omakaseBtn.classList.add("rolling", "cooldown");
    // 입력창을 잠그고 셔머 애니메이션으로 "생성 중"을 표시 — 잠그지 않으면 조회(최대 4초
    // 안팎, 위치·날씨 API) 도중 사용자가 직접 타이핑한 내용이 완료 시 덮어써지는 레이스
    // 컨디션이 생긴다.
    const prevPlaceholder = promptEl.placeholder;
    promptEl.disabled = true;
    promptEl.classList.add("prompt-generating");
    promptEl.placeholder = "오마카세 프롬프트 생성 중…";
    try {
      const ctx = await getOmakaseContext();
      promptEl.value = buildOmakasePrompt(ctx);
      promptEl.dispatchEvent(new Event("input"));
    } finally {
      promptEl.disabled = false;
      promptEl.classList.remove("prompt-generating");
      promptEl.placeholder = prevPlaceholder;
      // 쿨타임은 클릭 시점부터 5초 — 조회가 그보다 빨리 끝나도 버튼은 남은 시간만큼 더
      // 잠가둔다(시계방향으로 걷히는 CSS 파이 애니메이션과 실제 잠금 해제 시점을 일치시킴).
      const remaining = Math.max(0, OMAKASE_COOLDOWN_MS - (Date.now() - clickedAt));
      setTimeout(() => {
        omakaseBtn.disabled = false;
        omakaseBtn.classList.remove("cooldown");
      }, remaining);
    }
  });
}

// ── 요청 ─────────────────────────────────────────────────────────────────────
form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const body = {};

  if (currentMode === "ai") {
    // ── AI 모드: 프롬프트 필수 ──
    const prompt = $("prompt").value.trim();
    if (!prompt) return;
    body.prompt = prompt;
    body.mode = "ai";

    if (minutesTouched) {
      const minutes = parseInt($("target-minutes").value, 10);
      if (!Number.isNaN(minutes)) body.target_minutes = minutes;
    }

    const bands = collectBands();
    if (bands.length) body.bands = bands;
    const customStages = collectStages();
    if (customStages) body.stages = customStages;
    if (coverTouched) {
      Object.assign(body, typeToFlags(settingsType));
    }
  } else {
    // ── 커스텀 모드: 직접 구성한 stages 전송 ──
    body.mode = "custom";
    const customStages = collectStagesForCustomMode();
    if (!customStages || customStages.length === 0) {
      showError("구간 설정을 해 주세요.");
      return;
    }
    body.stages = customStages;

    if (minutesTouched) {
      const minutes = parseInt($("target-minutes").value, 10);
      if (!Number.isNaN(minutes)) body.target_minutes = minutes;
    }

    const bands = collectBands();
    if (bands.length) body.bands = bands;
    if (coverTouched) {
      Object.assign(body, typeToFlags(settingsType));
    }
  }

  showLoading(true);
  hide(errorEl);
  hide(resultEl);

  try {
    const res = await fetch(`${API_BASE}/api/setlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = await res.json().catch(() => null);
    if (res.status === 202) {
      // 큐잉(TPM 페이싱) 중 — job_id로 폴링해서 완료를 기다린다(architecture.md 스키마3 확장).
      data = await pollSetlistJob(data);
    } else if (!res.ok) {
      const msg = (data && data.error && data.error.message) || `요청 실패 (HTTP ${res.status})`;
      throw new Error(msg);
    }
    renderResult(data);
    // lastStages(width 포함)는 renderResult가 이미 채워둔다 — 여기서 다시 덮어쓰면
    // width 계산이 유실된다(재도입 금지).
  } catch (err) {
    const offline = err instanceof TypeError;
    showError(offline
      ? "백엔드에 연결하지 못했어요. 서버가 켜져 있는지, API 주소가 맞는지 확인해 주세요."
      : err.message);
  } finally {
    showLoading(false);
  }
});

// 큐 대기(TPM 페이싱) 폴링 — POST /api/setlist가 202+job_id를 주면(트래픽 몰려 리미터가
// 요청을 바로 못 받는 경우) GET .../status/{job_id}를 주기적으로 물어 완료를 기다린다.
// 예전엔 서버가 이 대기를 HTTP 요청 안에서 블로킹하다 20초 넘으면 그냥 429를 냈는데(사용자 피드백:
// "큐 대기 중인데 단순히 20초 넘어갔다고 429 처리하면 안 되지"), 이제 대기 자체는 서버 백그라운드
// 잡으로 옮기고 여기서 폴링하며 "몇 초 남음"을 계속 갱신해 보여준다.
const SETLIST_POLL_INTERVAL_MS = 1500;
const SETLIST_POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5분 — groq_adapter.py tpm_max_wait(180s)보다 여유

function setQueueWaitMessage(waitSeconds, queuePosition) {
  if (!loadingSubEl) return;
  const ahead = queuePosition > 0 ? `내 앞에 ${queuePosition}명 대기 중. ` : "";
  if (waitSeconds == null || waitSeconds <= 0) {
    loadingSubEl.textContent = ahead
      ? `${ahead}곧 시작할게요! 🙏`
      : "지금 요청이 몰려서 순서를 기다리고 있어요. 곧 시작할게요! 🙏";
    return;
  }
  const rounded = Math.max(1, Math.round(waitSeconds));
  loadingSubEl.textContent = `${ahead}약 ${rounded}초 정도 걸릴 것 같아요… ⏳`;
}

async function pollSetlistJob(initial) {
  const jobId = initial && initial.job_id;
  if (!jobId) throw new Error("대기열 등록에 실패했어요. 잠시 후 다시 시도해 주세요.");
  if (coldStartTimer) { clearTimeout(coldStartTimer); coldStartTimer = null; } // 콜드스타트 안내와 겹치지 않게
  setQueueWaitMessage(initial.estimated_wait_seconds, initial.queue_position);

  const deadline = Date.now() + SETLIST_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, SETLIST_POLL_INTERVAL_MS));
    const res = await fetch(`${API_BASE}/api/setlist/status/${jobId}`);
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (data && data.error && data.error.message) || `요청 실패 (HTTP ${res.status})`;
      throw new Error(msg);
    }
    if (data.status === "done") return data.result;
    setQueueWaitMessage(data.estimated_wait_seconds, data.queue_position);
  }
  throw new Error("대기 시간이 너무 길어져 요청을 취소했어요. 잠시 후 다시 시도해 주세요.");
}

// 대기 UX(트래픽/콜드스타트 대비): 로딩 중 문구를 위트있게 순환하고, 오래 걸리면(콜드스타트 추정)
// '서버 깨우는 중' 안내로 강화. 무료 플랜 슬립 시 첫 응답이 느려도 이탈을 줄인다.
const LOADING_MESSAGES = [
  "플레이리스트를 만드는 중입니다~ 🎶",
  "요청을 무드로 해석하고 있어요… 🔮",
  "곡을 하모닉하게 잇는 중… 🎼",
  "에너지 흐름을 다듬는 중… 📈",
  "당신을 위한 곡을 고르고 있어요… ✨",
];
const COLDSTART_SUB = "서버가 잠깐 자고 있었나 봐요… 깨우는 중이에요! 🥱☕ (유메와 파와—!)";
const LOADING_DEFAULT_SUB = "백엔드가 잠들어 있었다면 첫 응답이 조금 느릴 수 있어요.";
const loadingTextEl = loadingEl.querySelector(".loading-text");
const loadingSubEl = loadingEl.querySelector(".loading-sub");
let loadingRotateTimer = null;
let coldStartTimer = null;

// 세트리스트 생성 요청이 오가는 동안 AI 모드 프롬프트 입력창과 커스텀 모드 전체 파라미터를
// 잠근다 — 응답이 오기 전에 사용자가 값을 바꾸면, 화면(다음 요청에 실릴 값)과 방금 보낸
// 요청이 서로 다른 상태를 가리키는 레이스 컨디션이 생긴다.
function setFormLocked(locked) {
  promptEl.disabled = locked;
  if (omakaseBtn) omakaseBtn.disabled = locked;
  const modeSwitch = $("mode-switch");
  if (modeSwitch) modeSwitch.disabled = locked;
  const optionsDetails = $("options-details");
  if (optionsDetails) optionsDetails.classList.toggle("locked", locked);
}

function showLoading(on) {
  submitBtn.disabled = on;
  setFormLocked(on);
  toggle(loadingEl, on);
  if (on) startLoadingAnimation();
  else stopLoadingAnimation();
}

function startLoadingAnimation() {
  let i = 0;
  if (loadingTextEl) loadingTextEl.textContent = LOADING_MESSAGES[0];
  if (loadingSubEl) loadingSubEl.textContent = LOADING_DEFAULT_SUB;
  loadingRotateTimer = setInterval(() => {
    i = (i + 1) % LOADING_MESSAGES.length;
    if (loadingTextEl) loadingTextEl.textContent = LOADING_MESSAGES[i];
  }, 2200);
  // 8초 넘게 걸리면 콜드스타트로 보고 위트 멘트로 안내 강화.
  coldStartTimer = setTimeout(() => {
    if (loadingSubEl) loadingSubEl.textContent = COLDSTART_SUB;
  }, 8000);
}

function stopLoadingAnimation() {
  if (loadingRotateTimer) { clearInterval(loadingRotateTimer); loadingRotateTimer = null; }
  if (coldStartTimer) { clearTimeout(coldStartTimer); coldStartTimer = null; }
}
function showError(message) {
  errorEl.textContent = "⚠️ " + message;
  show(errorEl);
}

// ── 설정: 밴드 필터 · 단계 직접 지정 (§5-1) ────────────────────────────────────
const bandListEl = $("band-list");
const mapPadEl = $("map-pad");
const mapSvgEl = $("map-svg");
const timebarEl = $("timebar");
const timebarTicksEl = $("timebar-ticks");
const timebarTotalLabelEl = $("timebar-total-label");
const impressionRowEl = $("impression-row");
const stageNEl = $("stage-n");
const paramGraphsEl = $("param-graphs");
const bgToggleEl = $("bg-toggle");
const stagePlusBtn = $("stage-plus");
const stageMinusBtn = $("stage-minus");
let stageTouched = false; // 사용자가 그래프를 조정했는지 — 조정 전엔 LLM 에너지 자동 사용
// 사용자가 직접 건드린 설정만 요청에 override로 싣는다. 안 건드린 값은 생략 → LLM이 결정하고,
// 응답 후 그 값을 UI에 '반영'만 한다(다음 요청에 강제되지 않게 — 밴드 필터 패턴과 동일).
let minutesTouched = false;
let coverTouched = false;
let settingsType = "all"; // "all" | "original" | "cover" — 세 개 중 항상 정확히 하나만 켜짐(토글 버튼)

// 사용자가 '직접' 체크한 밴드만 요청 간 지속한다. 프롬프트 자동감지 밴드는 매 요청 일회성이어야
// 하므로(자연어 요청 = 매번 새 의도), 체크박스의 시각 상태와 분리해 별도 집합으로 추적한다.
// 이 집합은 오직 사용자의 change 이벤트로만 갱신 — 프로그램적 .checked 대입은 change를 발생시키지
// 않으므로 syncBandChecks가 여기 섞이지 않는다(요청 간 밴드 누적 버그의 근본 차단).
const manualBands = new Set();
// 감성 설정 구간별 밴드 셀렉터(#impression-row) 옵션 채우기용 — loadBands()가 채운다.
let cachedBands = [];

// 구간별 "밴드 고정" 팝업 상태 — buildImpressionRow()가 매 렌더마다 다시 채우지만, 열림
// 상태 추적과 바깥 클릭 감지는 재렌더에도 살아남아야 해서 최상위(모듈 스코프)에 둔다.
let impressionBandToggleEls = [];
let impressionBandPopupEls = [];
let openBandPopupIndex = -1;

function closeBandPopup() {
  if (openBandPopupIndex !== -1 && impressionBandPopupEls[openBandPopupIndex]) {
    impressionBandPopupEls[openBandPopupIndex].classList.add("hidden");
  }
  openBandPopupIndex = -1;
}
document.addEventListener("click", (e) => {
  if (openBandPopupIndex === -1) return;
  const popup = impressionBandPopupEls[openBandPopupIndex];
  const toggle = impressionBandToggleEls[openBandPopupIndex];
  if (popup && !popup.contains(e.target) && toggle && !toggle.contains(e.target)) {
    closeBandPopup();
  }
});

// 구간별 밴드 고정 팝업에 보여줄 밴드 목록 — 전역 밴드 필터에서 수동 선택한 것이 있으면
// 그것만, 없으면(=전체) 전체 밴드. "전역에서 선택한 모든 밴드"라는 사용자 요구사항 그대로.
function effectiveGlobalBandChoices() {
  const present = manualBands.size > 0 ? [...manualBands] : cachedBands.map((b) => b.band);
  return bandsInSelectorOrder(present);
}

// 구간별 밴드 고정 팝업 내용 채우기 — 전역 밴드 필터와 동일한 디자인(.band-list/.band-item)
// 재사용. 다중 선택(체크박스)이라 전역 필터와 달리 label에 이름을 병기하지 않고 아이콘+
// 곡수만(공간 절약, 툴팁으로 이름 확인) — 전역 밴드 필터와 동일한 관례.
function renderBandPopupOptions(popupEl, i) {
  popupEl.replaceChildren();
  const list = document.createElement("div");
  list.className = "band-list";
  const countByBand = new Map(cachedBands.map((b) => [b.band, b.count]));
  const seg = stageModel.segments[i];
  for (const band of effectiveGlobalBandChoices()) {
    const label = document.createElement("label");
    label.className = "band-item";
    label.title = prettyBand(band);
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "band-cb";
    cb.checked = (seg.bands || []).includes(band);
    cb.addEventListener("change", () => {
      stageTouched = true;
      const cur = new Set(stageModel.segments[i].bands || []);
      if (cb.checked) cur.add(band); else cur.delete(band);
      stageModel.segments[i].bands = [...cur];
      updateBandToggleIndicator(i);
    });
    const icon = makeBandIcon(band, "band-item-icon");
    const count = document.createElement("span");
    count.className = "band-item-count";
    count.textContent = countByBand.get(band) ?? "";
    label.append(cb, icon, count);
    list.appendChild(label);
  }
  popupEl.appendChild(list);
}

function updateBandToggleIndicator(i) {
  const btn = impressionBandToggleEls[i];
  if (!btn || !stageModel.segments[i]) return;
  btn.classList.toggle("on", (stageModel.segments[i].bands || []).length > 0);
}

// bandori-song-sorter와 동일한 밴드 나열 순서(아이콘 애셋은 assets/bands/<band>.png, 미포함은
// 뒤). renderStageGraph()가 페이지 로드 시 동기적으로 한 번 실행되며 구간별 밴드 셀렉터를
// 채우려고 이 함수를 곧바로 호출하므로, 파일 하단에 두면 TDZ(const 초기화 전 접근)로
// ReferenceError가 나 스크립트 전체가 중단된다(실사용 버그로 발견) — 반드시 최상단에 둘 것.
const BAND_ORDER = [
  "poppin_party", "afterglow", "pastel_palettes", "roselia",
  "hello_happy_world", "morfonica", "raise_a_suilen", "mygo",
  "ave_mujica", "mugendai_mutype", "millsage", "ikka_dumb_rock",
];
function bandsInSelectorOrder(present) {
  const ordered = BAND_ORDER.filter((b) => present.includes(b));
  const rest = present.filter((b) => !BAND_ORDER.includes(b)).sort();
  return [...ordered, ...rest];
}

async function loadBands() {
  try {
    const res = await fetch(`${API_BASE}/api/bands`);
    const data = await res.json();
    cachedBands = data.bands || [];
    renderBands(cachedBands);
    // 구간별 밴드 셀렉터는 이 응답이 오기 전에 이미 그려졌을 수 있어(비동기), 도착 즉시 갱신.
    if (stageModel) renderStageGraph();
  } catch (_) {
    bandListEl.textContent = "밴드 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).";
  }
}

function renderBands(bands) {
  bandListEl.replaceChildren();
  if (!bands.length) { bandListEl.textContent = "밴드 없음"; return; }
  // 표처럼 가지런한 그리드: 밴드 아이콘 + 곡 수(이름 생략, 툴팁으로 제공). 순서=BAND_ORDER.
  const countByBand = new Map(bands.map((b) => [b.band, b.count]));
  for (const band of bandsInSelectorOrder([...countByBand.keys()])) {
    const label = document.createElement("label");
    label.className = "band-item";
    label.title = prettyBand(band); // 이름은 툴팁으로
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = band;
    cb.className = "band-cb";
    // 사용자가 직접 토글한 것만 manualBands에 반영(요청 간 지속 대상). syncBandChecks의
    // 프로그램적 대입은 change를 발생시키지 않으므로 자동감지분은 여기 들어오지 않는다.
    cb.addEventListener("change", () => {
      if (cb.checked) manualBands.add(cb.value);
      else manualBands.delete(cb.value);
      syncStageBandsToGlobalFilter();
    });
    const icon = makeBandIcon(band, "band-item-icon");
    const count = document.createElement("span");
    count.className = "band-item-count";
    count.textContent = countByBand.get(band);
    label.append(cb, icon, count);
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
  syncStageBandsToGlobalFilter();
});

// 전역 밴드 필터가 바뀌면(체크·해제·전체 해제) 구간별 "밴드 고정" 선택도 즉시 반영한다
// (사용자 요구사항) — 더 이상 전역에서 유효하지 않은 구간별 선택은 정리하고, 열려 있는
// 팝업이 있으면 새 옵션으로 다시 그린다.
function syncStageBandsToGlobalFilter() {
  if (!stageModel) return;
  const allowed = new Set(effectiveGlobalBandChoices());
  stageModel.segments.forEach((s, i) => {
    if (s.bands && s.bands.length) {
      s.bands = s.bands.filter((b) => allowed.has(b));
    }
    updateBandToggleIndicator(i);
  });
  if (openBandPopupIndex !== -1 && impressionBandPopupEls[openBandPopupIndex]) {
    renderBandPopupOptions(impressionBandPopupEls[openBandPopupIndex], openBandPopupIndex);
  }
}

// 범용 유틸(트랙리스트·프리셋·플레이바 등 여러 곳에서 공유) — 2D 정서 지도 이식 과정에서
// 실수로 함께 지워졌던 것을 복원(elDiv/clamp 누락으로 결과 렌더링·재생바가 ReferenceError로 깨졌음).
function elDiv(cls) { const d = document.createElement("div"); d.className = cls; return d; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// 2D 정서 지도 + 시간 배분 + 고급 설정 편집기 (§5-1a)
const SVG_NS = "http://www.w3.org/2000/svg";
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const MAP_PAD = 8; // 지도 여백(%)
const toMapPct = (frac) => MAP_PAD + frac * (100 - MAP_PAD * 2);
const fromMapPct = (pct) => clamp01((pct - MAP_PAD) / (100 - MAP_PAD * 2));
const MIN_SEGMENTS = 2;  // 구간 최소 개수
const MAX_SEGMENTS = 11; // 구간 최대 개수
const DEFAULT_STAGE_COUNT = 3; // 기본 구간 수
const MIN_WIDTH_MIN = 3; // 구간 최소 길이(분) — 구간이 너무 촘촘해지면 곡 배정이 어색해짐

// 고급 설정 그래프 5개
const PARAM_DEFS = [
  { key: "lufs_integrated", label: "라우드니스", desc: "높을수록 크고 힘있는 곡이, 낮을수록 조용한 곡이 선택됩니다." },
  { key: "lra", label: "다이내믹 범위", desc: "높을수록 벅차는 느낌의 곡이, 낮을수록 일정한 느낌의 곡이 선택됩니다." },
  { key: "danceability_norm", label: "리듬감", desc: "높을수록 리드미컬한 곡이, 낮을수록 변칙적인 리듬의 곡이 선택됩니다." },
  { key: "instr_stem_ratio", label: "악기 비중", desc: "높을수록 악기 비중이 높은 곡이, 낮을수록 보컬 비중이 높은 곡이 선택됩니다." },
  { key: "speech_median", label: "음절밀도", desc: "높을수록 랩 성향의 곡이, 낮을수록 랩이 아닌 곡이 선택됩니다." },
];

// 고급 설정 그래프용 여백
const PAD_TOP = 10;      // 그래프 상하 여백(뷰박스 0~100 기준)
const PAD_BOTTOM = 6;
const valToY = (v) => PAD_TOP + (1 - v) * (100 - PAD_TOP - PAD_BOTTOM);
const yToVal = (fracY) => clamp01(1 - (fracY * 100 - PAD_TOP) / (100 - PAD_TOP - PAD_BOTTOM));

// stageModel: { totalMinutes, segments: [{energy, width, valence, lufs_integrated, lra, danceability_norm, instr_stem_ratio, speech_median}] }
let stageModel = null;

// 백엔드도 180분(3시간) 하드캡을 두지만(routes.py _MAX_TARGET_MINUTES), 여기서도 넘긴 순간
// 180으로 되돌리고 안내한다(number input의 native max는 스핀 버튼만 막고 타이핑은 안 막음).
minutesEl.addEventListener("input", () => {
  minutesTouched = true;
  const n = parseInt(minutesEl.value, 10);
  if (!Number.isNaN(n) && n > 180) {
    minutesEl.value = 180;
    minutesHintEl.textContent = "⚠️ 최대 3시간(180분)까지 설정할 수 있어요.";
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
    stageNEl.textContent = `${stageModel.segments.length}구간`;
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
    mapSvgEl.append(defs, gridG, path);

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
        `밝기 ${Math.round(s.valence * 100)} · 에너지 ${Math.round(s.energy * 100)}`;
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
    unit.textContent = "분";
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
  const IMPRESSION_PLACEHOLDER_EXAMPLES = [
    "설레고 두근거리는 마음",
    "지치고 무거운 마음을 다독이는 위로",
    "터질 듯한 흥분과 해방감",
    "쓸쓸하고 애틋한 그리움",
    "작은 희망을 붙잡는 담담한 의지",
  ];

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
      label.textContent = "구간";
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
      bandToggle.append(dot, document.createTextNode("밴드 고정"));
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
      svg.append(gridG, boundaryG, area, curve);
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

// ── 모드 전환 ─────────────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  const isAi = mode === "ai";

  // 스위치 손잡이 위치(체크 상태) 업데이트
  const modeSwitch = $("mode-switch");
  if (modeSwitch) modeSwitch.setAttribute("aria-checked", isAi ? "false" : "true");

  // 프롬프트 필드 표시/숨김. required도 함께 꺼야 한다 — 켜진 채로 두면 커스텀 모드에서
  // 빈 프롬프트input이 네이티브 HTML5 검증에 걸려 submit 이벤트 자체가 발생하지 않는다
  // (콘솔 에러도 안 남아 겉으로는 아무 반응도 없는 것처럼 보이는 버그였음).
  const promptField = $("prompt-field");
  if (promptField) {
    promptField.style.display = isAi ? "" : "none";
  }
  promptEl.required = isAi;

  // 세부 설정은 커스텀 모드 전용 화면으로 취급한다 — AI 모드에서는 통째로 숨기고,
  // 커스텀 모드에서는 항상 펼쳐서 보여준다(더 이상 접었다 펴는 선택 요소가 아님).
  const optionsDetails = $("options-details");
  if (optionsDetails) {
    optionsDetails.style.display = isAi ? "none" : "";
    if (isAi) {
      optionsDetails.classList.remove("force-open");
    } else {
      optionsDetails.classList.add("force-open");
      optionsDetails.open = true;
      prefillCustomFromLast();
    }
  }
}

function prefillCustomFromLast() {
  // 마지막 AI 생성 결과(lastStages)가 있으면 그것으로, 없으면 기본 0.5로.
  if (!lastStages || lastStages.length === 0) {
    // lastStages가 없으면 현재 stageModel로 초기화
    lastStages = stageModel?.segments.map(s => ({ ...s })) || [];
  }
  if (lastStages.length === 0) {
    stageTouched = false;
    renderStageGraph();
    return;
  }

  // lastStages는 두 출처를 가질 수 있어 형태가 다르다:
  //  (a) 위 폴백처럼 stageModel.segments를 그대로 복사한 경우 — energy/width 등 이미 정상 형태.
  //  (b) AI 모드 응답의 setlist.stages 에코 — 필드명이 energy_target(energy 아님)이고,
  //      신규 6개 파라미터는 AI가 채우지 않으면 전부 null. width는 renderResult가 실제
  //      곡 배정 비율(picks의 stage_index 개수)로 미리 채워두지만, 곡이 0개인 구간처럼
  //      드문 경우엔 없을 수 있어 그때만 균등폭(1/n)으로 폴백한다.
  //  (b)를 그대로 복사하면 energy/width가 undefined가 되고 신규 필드가 null인 채로 남아,
  //  이후 collectStagesForCustomMode()의 .toFixed() 호출이 크래시한다(실사용 버그로 발견됨).
  const n = lastStages.length;
  const mapped = lastStages.map((s) => ({
    width: s.width != null ? s.width : 1 / n,
    energy: s.energy != null ? s.energy : (s.energy_target != null ? s.energy_target : 0.5),
    valence: s.valence != null ? s.valence : 0.5,
    lufs_integrated: s.lufs_integrated != null ? s.lufs_integrated : 0.5,
    lra: s.lra != null ? s.lra : 0.5,
    danceability_norm: s.danceability_norm != null ? s.danceability_norm : 0.5,
    instr_stem_ratio: s.instr_stem_ratio != null ? s.instr_stem_ratio : 0.5,
    speech_median: s.speech_median != null ? s.speech_median : 0.5,
    impression: s.impression || "",
    bands: s.bands && s.bands.length ? s.bands : [],
  }));

  if (!stageModel) initStageModel(n);
  stageModel.segments = mapped;

  stageTouched = false;
  renderStageGraph();
}

function collectStagesForCustomMode() {
  // 커스텀 모드: stageTouched 체크 없이 항상 모든 segments 반환
  // (사용자가 그대로 제출해도 정상 동작)
  if (!stageModel) return null;
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

// ── 초기화 ─────────────────────────────────────────────────────────────────────
loadBands();
initStageModel();
initStageControls(); // 버튼 이벤트 한 번 붙이기

// 모드 스위치 리스너 (한 번만 붙이기) — 두 상태뿐이라 클릭할 때마다 반대 모드로 토글
const modeSwitchEl = $("mode-switch");
if (modeSwitchEl) {
  modeSwitchEl.addEventListener("click", () => {
    setMode(currentMode === "ai" ? "custom" : "ai");
  });
}

setMode(currentMode); // 초기 모드 상태 적용 — 안 하면 AI 모드인데 세부설정이 보인다

// DEPRECATED(디버깅용) — AI 해석 결과가 UI/의도와 어긋날 때 원인 추적용. epic 3단계
// stage_params 튜닝이 끝나면 버튼과 이 핸들러를 통째로 제거할 것.
const debugCopyBtn = $("debug-copy-state-btn");
if (debugCopyBtn) {
  debugCopyBtn.addEventListener("click", async () => {
    const snapshot = {
      prompt: promptEl.value.trim(),
      mode: currentMode,
      target_minutes: stageModel ? stageModel.totalMinutes : null,
      bands: collectBands(),
      song_type: settingsType,
      // 지금 그래프 상태(구간별 energy/valence + 신규 6개 지표, 커스텀 모드 제출 형식과 동일).
      current_stages: collectStagesForCustomMode(),
      // 마지막으로 백엔드(LLM)가 실제로 반환한 해석 결과 — UI가 이를 어떻게 반영했는지 대조용.
      last_ai_params: lastParams,
      last_ai_stages: lastStages,
      last_applied_bands: lastAppliedBands,
    };
    const json = JSON.stringify(snapshot, null, 2);
    try {
      await navigator.clipboard.writeText(json);
      debugCopyBtn.textContent = "✅ 복사됨";
    } catch (_) {
      debugCopyBtn.textContent = "⚠️ 복사 실패(콘솔 확인)";
      console.log(json);
    }
    setTimeout(() => { debugCopyBtn.textContent = "🐛 현재 상태 복사 (디버그)"; }, 1500);
  });
}

renderStageGraph(); // 그래프는 세부설정에서 상시 표시(토글 없음)

// 메뉴 안 버전 표기 = "v메인버전 - 커밋SHA". 배포 프론트는 빌드시 __COMMIT__을 SHA로,
// __VERSION__을 최신 git 태그(v1.2.3)로 주입하고, 로컬(또는 주입 실패) 시엔 백엔드
// /api/health의 version(RENDER_GIT_COMMIT 또는 git)을 커밋 SHA 대신 가져온다.
(async function initVersion() {
  const el = $("app-version");
  if (!el) return;
  const rawCommit = window.APP_VERSION || "";
  let commit = rawCommit && rawCommit !== "__COMMIT__" ? rawCommit.slice(0, 7) : "";
  if (!commit) {
    try {
      const res = await fetch(`${API_BASE}/api/health`);
      const d = await res.json();
      commit = (d && d.version) || "dev";
    } catch (_) { commit = "dev"; }
  }
  const rawMain = window.APP_MAIN_VERSION || "";
  const mainVer = rawMain && rawMain !== "__VERSION__" ? rawMain : "";
  el.textContent = mainVer ? `${mainVer} - ${commit}` : commit;
  if (commit && commit !== "dev" && window.APP_REPO) el.href = `${window.APP_REPO}/commit/${commit}`;
  else el.removeAttribute("href");
})();

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
  clearEditUndos(); // 새 플레이리스트 → 편집 되돌리기 리셋(프리셋 삭제 되돌리기는 유지)

  if (!picks.length) {
    showError("조건에 맞는 곡을 찾지 못했어요. 요청을 조금 바꿔 보세요.");
    return;
  }

  lastParams = data.params || {};
  lastAppliedBands = data.applied_bands || [];
  // data.params.stage_minutes는 LLM의 '의도'일 뿐, 실제 적용 결과(완충 노드로 슬롯이 건너뛰어질
  // 수 있음 등)와 다를 수 있다 — 그래서 width는 여기서 실제 곡 배정 결과(picks의 stage_index별
  // 개수)로 직접 계산한다. 이렇게 안 하면 커스텀 모드 프리필(prefillCustomFromLast)이 항상
  // 균등폭(1/n)으로 되돌아가 "마지막 구간만 길게" 같은 요청이 커스텀 모드로 넘어오면서 사라져
  // 보인다(실사용 버그로 발견). stage_minutes 자체는 디버그 스냅샷(last_ai_params)에서 확인 가능.
  lastStages = (data.stages || []).map((s, i) => {
    const count = picks.filter((p) => p.stage_index === i).length;
    return count > 0 ? { ...s, width: count / picks.length } : { ...s };
  });

  // 백엔드가 재생 형태 override를 존중하지 않았다면(1회차·의도 변경 → honored_overrides=false) 사용자가
  // 만졌던 '재생 형태' 플래그를 풀어, 그래프·재생시간이 새 해석을 반영하도록 한다(고착 방지). 밴드·커버는
  // 스코프 필터라 항상 유지(리셋하지 않음). 프리셋 복원(honored_overrides 없음)에는 영향 없음(=== false).
  if (data.honored_overrides === false) {
    stageTouched = false;
    minutesTouched = false;
  }

  renderSummary(data);
  renderTracklist(picks);
  renderCamelotWheel(picks);
  syncBandChecks(data.applied_bands); // 적용된 밴드(프롬프트 자동감지 포함)를 체크박스에 반영
  syncGraphToParams(data.params, lastStages); // 그래프에 이번 해석 아크(실제 사용된 전 지표) 반영(미조정 시)
  reflectSettings(data); // 재생시간·단계 수·커버 필터를 세부 설정 UI에 반영(미조정 시)
  show(resultEl);
  showPlaybar();

  track("playlist_created", { count: picks.length, minutes: Math.round(estimatedTotal / 60) });

  startPlayback();

  if (!restoring) autoSaveOnGenerate(); // 새 생성 시에만 새 프리셋(복원 시엔 생략)
}

// 모델이 정한 파라미터(재생시간·단계 수·커버 필터)를 세부 설정 UI에 반영한다.
// 사용자가 직접 건드린 값(touched)은 덮지 않는다. 프로그램적 대입이라 change/input 미발생 →
// touched 플래그가 오염되지 않아 다음 요청에 강제 override로 새지 않는다(밴드 필터 패턴과 동일).
function reflectSettings(data) {
  const p = data.params || {};
  if (!minutesTouched && typeof p.target_minutes === "number") {
    $("target-minutes").value = p.target_minutes;
    if (stageModel) { stageModel.totalMinutes = p.target_minutes; }
  }
  if (!coverTouched) {
    settingsType = flagsToType(data.include_original !== false, data.include_cover === true);
    renderSettingsTypeFilter();
  }
}

function renderSummary(data) {
  const p = data.params || {};
  summaryEl.replaceChildren();

  const interp = document.createElement("p");
  interp.className = "interp";
  interp.textContent = p.interpretation_summary || "요청에 맞춰 세트리스트를 구성했어요.";
  summaryEl.appendChild(interp);

  // 인스타그램식 해시태그(최대 5개).
  const tags = Array.isArray(p.tags) ? p.tags.slice(0, 5) : [];
  if (tags.length) {
    const tagRow = document.createElement("div");
    tagRow.className = "tags";
    for (const t of tags) {
      const span = document.createElement("span");
      span.className = "tag";
      span.textContent = "#" + String(t).replace(/^#+/, "").trim();
      tagRow.appendChild(span);
    }
    summaryEl.appendChild(tagRow);
  }

  // 실용 메타만(곡수·재생시간). 밝기/에너지 수치는 플레이버·태그로 대체.
  const meta = document.createElement("div");
  meta.className = "meta";
  const mins = Math.round(estimatedTotal / 60);
  for (const c of [`${picks.length}곡`, `약 ${mins}분`]) {
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
    li.addEventListener("click", () => {
      // 길게누름으로 메뉴가 뜬 직후의 클릭(release)은 재생으로 이어지지 않도록 무시.
      if (trackLongPressFired) { trackLongPressFired = false; return; }
      playSong(i, false);
    });

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

    const badges = document.createElement("div");
    badges.className = "badges";
    const h = p.reason ? p.reason.harmonic : "";
    badges.appendChild(makeBadge(h, harmonicLabelKo(h), harmonicTooltipKo(h)));
    badges.appendChild(makeBadge("key", keyLabel(p.camelot), "조성(Camelot " + (p.camelot || "") + ")"));
    for (const { key, label } of PICK_PARAM_DEFS) {
      if (typeof p[key] === "number") badges.appendChild(makeParamBadge(label, p[key]));
    }

    bodyEl.append(title, band, badges);
    attachTrackLongPress(bodyEl, i); // 우클릭·길게누름 → "다음 곡 추가"/"현재 곡 제거" 메뉴
    li.append(pos, bodyEl, makeTrackActions(li, i));
    li.appendChild(makeInserter(i + 1)); // 이 트랙 '다음'(배열 index i+1) 삽입점
    tracklistEl.appendChild(li);
  });
}

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

// ── 트랙 우클릭·길게누름 메뉴("다음 곡 추가"/"현재 곡 제거") ─────────────────────
// attachGraphMenu(그래프 구간 메뉴)와 동일한 구조: pointerdown 시 타이머 예약 → 10px 초과
// 이동 시 취소 → 시간 초과 시 clamp된 위치에 메뉴 표시. bodyEl(제목 영역)에만 걸어 이동 핸들
// (track-move)·제거버튼(track-remove)·인서터(+)와는 겹치지 않는다. renderTracklist가 매 렌더마다
// 새 li/bodyEl을 만들므로(위 replaceChildren) 리스너가 누적되지 않는다.
let trackMenuEl = null;
let trackLongPressFired = false;

function closeTrackMenu() {
  if (trackMenuEl) { trackMenuEl.remove(); trackMenuEl = null; }
}

function openTrackMenu(clientX, clientY, items) {
  closeTrackMenu();
  const menu = elDiv("graph-menu"); // 기존 컨텍스트 메뉴 스타일 재사용
  for (const it of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "graph-menu-item";
    b.textContent = it.label;
    b.addEventListener("click", () => { closeTrackMenu(); it.onClick(); });
    menu.appendChild(b);
  }
  menu.style.visibility = "hidden"; // 측정 후 위치 보정
  document.body.appendChild(menu);
  const r = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(clientX, window.innerWidth - r.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(clientY, window.innerHeight - r.height - 8))}px`;
  menu.style.visibility = "";
  trackMenuEl = menu;
}

document.addEventListener("pointerdown", (e) => {
  if (trackMenuEl && !trackMenuEl.contains(e.target)) closeTrackMenu();
}, true);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeTrackMenu(); });
window.addEventListener("scroll", () => closeTrackMenu(), true);

let trackLpTimer = null;
let trackLpStartXY = null;
function clearTrackLongPress() { if (trackLpTimer) { clearTimeout(trackLpTimer); trackLpTimer = null; } trackLpStartXY = null; }
document.addEventListener("pointermove", (e) => {
  if (trackLpStartXY && Math.hypot(e.clientX - trackLpStartXY.x, e.clientY - trackLpStartXY.y) > 10) clearTrackLongPress();
}, true);
document.addEventListener("pointerup", clearTrackLongPress, true);
document.addEventListener("pointercancel", clearTrackLongPress, true);

function attachTrackLongPress(bodyEl, index) {
  const openFor = (clientX, clientY) => {
    openTrackMenu(clientX, clientY, [
      { label: "다음 곡 추가", onClick: () => openSongPickerAt(index + 1) },
      { label: "현재 곡 제거", onClick: () => removeSong(index) },
    ]);
  };
  bodyEl.addEventListener("contextmenu", (e) => { e.preventDefault(); openFor(e.clientX, e.clientY); });
  bodyEl.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse") return; // 데스크톱은 contextmenu(우클릭) 사용
    trackLongPressFired = false; // 새 제스처 시작 — 이전 제스처의 잔여 플래그 정리
    const x = e.clientX, y = e.clientY;
    if (trackLpTimer) clearTimeout(trackLpTimer);
    trackLpStartXY = { x, y };
    trackLpTimer = setTimeout(() => {
      trackLpTimer = null;
      trackLongPressFired = true;
      openFor(x, y);
    }, LONGPRESS_MS);
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

// 모바일은 호버가 없어 배지 툴팁을 탭으로 열고 닫는다(호버 가능한 기기는 mouseenter로도 열림).
// 툴팁 본체는 고정(fixed) 위치의 재사용 엘리먼트 1개 — 열 때마다 배지 위치를 재서
// 화면 가장자리에 잘리지 않게 좌우/상하로 클램프한다(창 크기·기기 방향에 맞춰 적응).
let openTooltipBadge = null;
let tooltipBox = null;
let tooltipText = null;
let tooltipArrow = null;
const TOOLTIP_MARGIN = 8;
const supportsHoverTooltip =
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: hover) and (pointer: fine)").matches;

function ensureTooltipEl() {
  if (!tooltipBox) {
    tooltipBox = document.createElement("div");
    tooltipBox.className = "badge-tooltip";
    tooltipText = document.createElement("span");
    tooltipArrow = document.createElement("div");
    tooltipArrow.className = "arrow";
    tooltipBox.append(tooltipText, tooltipArrow);
    document.body.appendChild(tooltipBox);
  }
  return tooltipBox;
}

function positionTooltip(badgeEl) {
  const box = ensureTooltipEl();
  const rect = badgeEl.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const boxW = box.offsetWidth;
  const boxH = box.offsetHeight;

  let placeBelow = false;
  let top = rect.top - boxH - TOOLTIP_MARGIN;
  if (top < TOOLTIP_MARGIN) {
    placeBelow = true;
    top = rect.bottom + TOOLTIP_MARGIN;
  }
  top = Math.min(Math.max(top, TOOLTIP_MARGIN), Math.max(TOOLTIP_MARGIN, vh - boxH - TOOLTIP_MARGIN));

  const badgeCenterX = rect.left + rect.width / 2;
  let left = badgeCenterX - boxW / 2;
  left = Math.min(Math.max(left, TOOLTIP_MARGIN), vw - boxW - TOOLTIP_MARGIN);

  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
  box.classList.toggle("above", !placeBelow);
  box.classList.toggle("below", placeBelow);

  // 화살표는 박스가 가장자리에서 밀려도 배지 중심을 계속 가리키도록 별도 보정.
  const arrowLeft = Math.min(Math.max(badgeCenterX - left, 12), boxW - 12);
  tooltipArrow.style.left = `${arrowLeft}px`;
}

function showTooltip(badgeEl, text) {
  const box = ensureTooltipEl();
  tooltipText.textContent = text;
  box.classList.add("visible");
  positionTooltip(badgeEl); // visible 처리 후 측정해야 offsetWidth/Height가 정확함
}

function hideTooltipBox() {
  if (tooltipBox) tooltipBox.classList.remove("visible");
}

function closeOpenTooltip() {
  openTooltipBadge = null;
  hideTooltipBox();
}

window.addEventListener("resize", () => {
  if (openTooltipBadge) positionTooltip(openTooltipBadge);
});

// 툴팁이 열려 있을 때는 화면 어디를 클릭하든(다른 배지 포함) 그 클릭은 툴팁만 닫고
// 원래 하려던 동작(곡 재생 등)으로 이어지지 않는다 — capture 단계에서 가로채 전파를 끊는다.
document.addEventListener(
  "click",
  (e) => {
    if (openTooltipBadge) {
      e.preventDefault();
      e.stopPropagation();
      closeOpenTooltip();
    }
  },
  true,
);

function makeBadge(kind, label, tooltip) {
  const b = document.createElement("span");
  b.className = "badge" + (kind ? " " + kind : "");
  b.textContent = label;
  if (tooltip) {
    b.dataset.tooltip = tooltip;
    b.tabIndex = 0; // 키보드 포커스로도 툴팁 확인 가능
    b.addEventListener("click", (e) => {
      e.stopPropagation(); // 태그 클릭이 트랙 재생(행 클릭)으로 전파되지 않도록
      const willOpen = openTooltipBadge !== b;
      closeOpenTooltip();
      if (willOpen) {
        showTooltip(b, tooltip);
        openTooltipBadge = b;
      }
    });
    if (supportsHoverTooltip) {
      b.addEventListener("mouseenter", () => showTooltip(b, tooltip));
      b.addEventListener("mouseleave", () => {
        if (openTooltipBadge !== b) hideTooltipBox();
      });
    }
    b.addEventListener("focus", () => showTooltip(b, tooltip));
    b.addEventListener("blur", () => {
      if (openTooltipBadge !== b) hideTooltipBox();
    });
  }
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
    setPlaybarPlaying(true);
    startPlaybarProgressTimer();
  } else if (e.data === YT.PlayerState.PAUSED) {
    setPlaybarPlaying(false);
    stopPlaybarProgressTimer();
  } else if (e.data === YT.PlayerState.ENDED) {
    stopPlaybarProgressTimer();
    setPlaybarPlaying(false);
    playedSeconds += safeDuration();
    maybeFireHalf();
    if (repeatMode === "one") {
      player.seekTo(0, true);
      player.playVideo();
    } else if (current + 1 < picks.length) {
      playSong(current + 1, true);
    } else if (repeatMode === "all") {
      playSong(0, true); // 마지막 곡까지 다 돌았으면 처음으로
    }
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
  highlight(index, auto);
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
  autoSaveOnEdit();
}

// − 버튼: 해당 곡 제거. 재생 중이던 곡이면 reconcilePlayer가 다음 곡으로 넘긴다.
function removeSong(index) {
  if (index < 0 || index >= picks.length) return;
  pushHistory();
  picks.splice(index, 1);
  if (!picks.length) {
    hide(resultEl);
    hidePlaybar();
    showError("모든 곡을 제거했어요. 새 요청을 만들거나 되돌리기(Ctrl+Z) 하세요.");
    return;
  }
  renderTracklist(picks);
  reconcilePlayer();
  syncGraphToEdited();
  autoSaveOnEdit();
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
  undoStack.push({ kind: "edit", picks: picks.slice(), current });
  capUndo();
}
function capUndo() {
  while (undoStack.length > 60) undoStack.shift();
}
// 새 플레이리스트 시 'edit' 되돌리기만 제거(프리셋 삭제 되돌리기는 유지).
function clearEditUndos() {
  for (let i = undoStack.length - 1; i >= 0; i--) {
    if (undoStack[i].kind === "edit") undoStack.splice(i, 1);
  }
}

// Ctrl/Cmd+Z — 최근 되돌리기(편집 상태 복원 또는 프리셋 삭제 취소). 텍스트 입력 중엔 기본 양보.
document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.shiftKey) return;
  if (e.key !== "z" && e.key !== "Z") return;
  const tag = (document.activeElement && document.activeElement.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (!undoStack.length) return;
  e.preventDefault();
  const action = undoStack.pop();
  if (action.kind === "preset-delete") {
    undoPresetDelete(action);
    return;
  }
  // kind === 'edit' — 편집 직전 상태 복원.
  picks = action.picks;
  current = action.current;
  hide(errorEl);
  show(resultEl); // 전부 제거 후 되돌리기면 결과 다시 표시
  showPlaybar();
  renderTracklist(picks);
  reconcilePlayer();
  syncGraphToEdited();
  autoSaveOnEdit(); // 되돌린 상태를 현재 프리셋에 반영
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
    const origSlice = stageModel.segments.slice(startIdx, Math.max(endIdx, startIdx + 1));
    const pickSlice = picks.slice(startIdx, Math.max(endIdx, startIdx + 1));

    // energy: 원래 선택된 곡들의 평균
    const energyMean = pickSlice.reduce((a, p) => a + (typeof p.energy === "number" ? p.energy : 0), 0) / pickSlice.length;

    // 나머지 6개 필드: 해당 구간의 원래 stage 값들의 평균 (또는 없으면 0.5)
    const getFieldMean = (fieldName) => {
      if (!origSlice.length) return 0.5;
      return origSlice.reduce((a, s) => a + (typeof s[fieldName] === "number" ? s[fieldName] : 0.5), 0) / origSlice.length;
    };

    segments.push({
      energy: clamp01(+energyMean.toFixed(2)),
      width: (endIdx - startIdx) / picks.length,
      valence: clamp01(+getFieldMean("valence").toFixed(2)),
      lufs_integrated: clamp01(+getFieldMean("lufs_integrated").toFixed(2)),
      lra: clamp01(+getFieldMean("lra").toFixed(2)),
      danceability_norm: clamp01(+getFieldMean("danceability_norm").toFixed(2)),
      instr_stem_ratio: clamp01(+getFieldMean("instr_stem_ratio").toFixed(2)),
      speech_median: clamp01(+getFieldMean("speech_median").toFixed(2)),
    });
  }
  const wsum = segments.reduce((a, s) => a + s.width, 0) || 1;
  segments.forEach((s) => (s.width = s.width / wsum));
  stageModel = { totalMinutes: stageModel.totalMinutes, segments };
  renderStageGraph();
}

// ── 프리셋(로컬 저장) — 좌측 메뉴에서 저장된 플레이리스트 열람·복원·삭제 (사용자 제안 B3) ────
// localStorage에 최대 50개 저장. 생성·이동·제거·추가 시 자동저장(현재 세션 프리셋 갱신).
// 형제 프로젝트가 랭크 진행률을 localStorage로 보존하는 방식과 동일.
const PRESETS_KEY = "setlist-presets-v1";
const PRESET_CAP = 50;

const menuBtn = $("menu-btn");
const menuPanel = $("menu-panel");
const menuScrim = $("menu-scrim");
const presetListEl = $("preset-list");
const presetEmptyEl = $("preset-empty");

function loadPresets() {
  try { return JSON.parse(localStorage.getItem(PRESETS_KEY)) || []; }
  catch (_) { return []; }
}
function persistPresets(arr) {
  try { localStorage.setItem(PRESETS_KEY, JSON.stringify(arr)); }
  catch (_) {/* 용량 초과/비활성(시크릿 모드) — 무시 */}
}

// 현재 플레이리스트 전체 상태 스냅샷(복원용). renderResult(data)와 같은 형태.
function currentSnapshot() {
  return {
    picks,
    params: lastParams,
    estimated_total_seconds: estimatedTotal,
    applied_bands: lastAppliedBands,
    stages: lastStages,
  };
}

function genPresetId() {
  return "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
}

function autoSaveOnGenerate() {
  currentPresetId = genPresetId();
  upsertPreset(currentPresetId);
}
function autoSaveOnEdit() {
  if (currentPresetId == null) return; // 프리셋 세션 없음 — skip
  upsertPreset(currentPresetId);
}

// 프리셋 생성/갱신. 없으면 맨 앞에 추가(초과 시 오래된 것 제거), 있으면 제자리 갱신.
function upsertPreset(id) {
  const arr = loadPresets();
  const title = (lastParams && lastParams.interpretation_summary) || "플레이리스트";
  const data = JSON.parse(JSON.stringify(currentSnapshot())); // 라이브 상태와 참조 분리
  const idx = arr.findIndex((p) => p.id === id);
  if (idx >= 0) {
    arr[idx] = { ...arr[idx], title, data }; // 위치·savedAt 유지
  } else {
    arr.unshift({ id, title, savedAt: Date.now(), data });
    if (arr.length > PRESET_CAP) arr.length = PRESET_CAP;
  }
  persistPresets(arr);
  renderPresetList();
}

function deletePreset(id) {
  const arr = loadPresets();
  const idx = arr.findIndex((p) => p.id === id);
  if (idx < 0) return;
  const [removed] = arr.splice(idx, 1);
  persistPresets(arr);
  if (currentPresetId === id) currentPresetId = null; // 현재 세션 프리셋이 삭제됨
  undoStack.push({ kind: "preset-delete", preset: removed, index: idx });
  capUndo();
  renderPresetList();
}

function undoPresetDelete(action) {
  const arr = loadPresets();
  arr.splice(Math.min(action.index, arr.length), 0, action.preset);
  if (arr.length > PRESET_CAP) arr.length = PRESET_CAP;
  persistPresets(arr);
  openMenu(); // 되돌린 프리셋을 보여주기 위해 메뉴 열기(renderPresetList 포함)
}

function restorePreset(id) {
  const p = loadPresets().find((x) => x.id === id);
  if (!p || !p.data) return;
  restoring = true;
  try { renderResult(p.data); } finally { restoring = false; }
  currentPresetId = id; // 이후 편집은 이 프리셋을 갱신
  closeMenu();
}

function relTime(ts) {
  const s = Math.max(0, (Date.now() - (ts || 0)) / 1000);
  if (s < 60) return "방금 전";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}

function renderPresetList() {
  if (!presetListEl) return;
  const arr = loadPresets();
  presetListEl.replaceChildren();
  if (presetEmptyEl) presetEmptyEl.hidden = arr.length > 0;
  for (const p of arr) {
    const li = document.createElement("li");
    li.className = "preset-item";

    const open = document.createElement("button");
    open.type = "button";
    open.className = "preset-open";
    const title = elDiv("preset-title");
    title.textContent = p.title || "플레이리스트";
    const meta = elDiv("preset-meta");
    const count = (p.data && p.data.picks && p.data.picks.length) || 0;
    meta.textContent = `${relTime(p.savedAt)} · ${count}곡`;
    open.append(title, meta);
    open.addEventListener("click", () => restorePreset(p.id));

    const del = document.createElement("button");
    del.type = "button";
    del.className = "preset-del";
    del.title = "삭제";
    del.setAttribute("aria-label", "프리셋 삭제");
    del.innerHTML =
      '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M2.8 4.3 H13.2 M6.4 4.3 V3 H9.6 V4.3 M4.6 4.3 L5.2 13 H10.8 L11.4 4.3"/></svg>';
    del.addEventListener("click", (e) => { e.stopPropagation(); deletePreset(p.id); });

    li.append(open, del);
    presetListEl.appendChild(li);
  }
}

// 좌상단 메뉴(햄버거 ↔ X) — 좌측 슬라이드 패널에서 프리셋 열람.
let menuOpen = false;
function openMenu() {
  menuOpen = true;
  if (menuBtn) { menuBtn.classList.add("open"); menuBtn.setAttribute("aria-expanded", "true"); menuBtn.setAttribute("aria-label", "메뉴 닫기"); }
  if (menuPanel) { menuPanel.classList.add("open"); menuPanel.setAttribute("aria-hidden", "false"); }
  if (menuScrim) menuScrim.hidden = false;
  renderPresetList();
}
function closeMenu() {
  menuOpen = false;
  if (menuBtn) { menuBtn.classList.remove("open"); menuBtn.setAttribute("aria-expanded", "false"); menuBtn.setAttribute("aria-label", "메뉴 열기"); }
  if (menuPanel) { menuPanel.classList.remove("open"); menuPanel.setAttribute("aria-hidden", "true"); }
  if (menuScrim) menuScrim.hidden = true;
}
if (menuBtn) menuBtn.addEventListener("click", () => (menuOpen ? closeMenu() : openMenu()));
if (menuScrim) menuScrim.addEventListener("click", closeMenu);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && menuOpen) closeMenu();
});

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
let pickerType = "all";   // "all" | "original" | "cover" — 곡 종류 필터

// 커버곡 판정 — 제목의 '(Cover)' 표기 기준(데이터 관례). 백엔드 routes.py의 _is_cover와 동일 규칙.
function isCoverSong(song) {
  return song.song.toLowerCase().includes("(cover)");
}

const BAND_ICON_BASE = "assets/bands";

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
  pickerType = "all";
  pickerSearchEl.value = "";
  pickerWhereEl.textContent = atIndex <= 0 ? "맨 앞에 삽입" : `${atIndex}번 다음에 삽입`;
  show(pickerEl);
  lockBodyScroll(true);
  pickerBandsEl.replaceChildren();
  pickerSongsEl.replaceChildren();
  pickerSongsEl.textContent = "곡 목록 불러오는 중…";
  renderPickerTypeFilter();
  try {
    await ensureSongs();
    renderPickerBands();
    renderPickerSongs();
    pickerSearchEl.focus();
  } catch (_) {
    pickerSongsEl.textContent = "곡 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).";
  }
}

function renderPickerTypeFilter() {
  const el = $("picker-type-filter");
  el.replaceChildren();
  for (const { key, label } of PICKER_TYPE_OPTIONS) {
    const pill = document.createElement("button");
    pill.type = "button";
    pill.className = "picker-type-pill" + (pickerType === key ? " active" : "");
    pill.textContent = label;
    pill.addEventListener("click", () => {
      if (pickerType === key) return;
      pickerType = key;
      renderPickerTypeFilter();
      renderPickerSongs();
    });
    el.appendChild(pill);
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
    if (pickerType !== "all" && isCoverSong(s) !== (pickerType === "cover")) return false;
    if (!q) return true;
    return s.song.toLowerCase().includes(q)
      || prettyBand(s.band).toLowerCase().includes(q)
      || s.band.toLowerCase().includes(q)
      // 로마자/한글 음차/한자음 검색(구버전 백엔드엔 필드가 없을 수 있음 — optional chaining으로 안전 처리).
      || (s.song_romaji?.toLowerCase().includes(q) ?? false)
      || (s.song_hangul?.toLowerCase().includes(q) ?? false)
      // 장음(ー) 변형 병기 필드 — 원문 음차("카아네에숀")와 한국식 관용("카네이션") 모두 매칭.
      || (s.song_hangul_search?.toLowerCase().includes(q) ?? false)
      || (s.song_hanja_reading?.toLowerCase().includes(q) ?? false);
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
    meta.textContent = `${prettyBand(s.band)} · ${keyLabel(s.camelot)} · 에너지 ${fmtNum(s.energy)}`;
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
  autoSaveOnEdit();
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
      prev_camelot: null, param_fit: 0, text: "직접 추가한 곡",
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

// 전체 세트리스트 공유(B2) — 'YouTube 재생목록' 버튼 → 공유 팝업(안내·URL 복사·내 재생목록에 넣기).
// URL 복사는 watch_videos 익명 링크(OAuth 불필요). '내 재생목록에 넣기'는 사용자 자신의 Google
// 계정에 실제 YouTube 재생목록을 생성한다(OAuth + Data API, 클라이언트 사이드 토큰 플로우).
const shareModalEl = $("share-modal");
const shareUrlInputEl = $("share-url");
const ytSaveStatusEl = $("yt-save-status");
const ytOpenLinkEl = $("yt-open-link");
const ytSaveProgressEl = $("yt-save-progress");
const ytSaveProgressBarEl = $("yt-save-progress-bar");
let shareUrl = "";

$("yt-playlist-btn").addEventListener("click", () => {
  if (!picks.length) return;
  const ids = picks.map((p) => p.video_id).join(",");
  shareUrl = `https://www.youtube.com/watch_videos?video_ids=${ids}`;
  shareUrlInputEl.value = shareUrl;
  resetCopyBtn();
  hide(ytSaveStatusEl);
  hide(ytOpenLinkEl); // 지난 회차의 결과 링크가 남지 않도록 초기화
  show(shareModalEl);
  lockBodyScroll(true);
  track("playlist_shared", { count: picks.length });
});

$("share-open").addEventListener("click", saveToYouTubePlaylist);
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

// ── '내 재생목록에 넣기' — Google OAuth(GIS 토큰 클라이언트) + YouTube Data API v3 ──────────────
// 백엔드 미관여(client secret 없음, 브라우저에서 직접 access token 발급·API 호출). 실패 시
// picks/현재 재생 상태는 절대 건드리지 않고 조기 반환한다(요구사항: 앱 상태 그대로 유지).
const YT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl";
let ytAccessToken = null;
let ytTokenClient = null;
let ytTokenPending = null; // 진행 중인 토큰 요청의 { resolve, reject } — 콜백에서 한 번만 결착
let ytSaving = false;      // 저장 진행 중 재진입 방지

function settleToken(ok, value) {
  if (!ytTokenPending) return;
  const pending = ytTokenPending;
  ytTokenPending = null;
  if (ok) pending.resolve(value);
  else pending.reject(value);
}

function getYouTubeTokenClient() {
  if (!ytTokenClient) {
    ytTokenClient = google.accounts.oauth2.initTokenClient({
      client_id: window.GOOGLE_CLIENT_ID,
      scope: YT_SCOPE,
      callback: (resp) => {
        if (resp && resp.error) settleToken(false, new Error(resp.error));
        else { ytAccessToken = resp.access_token; settleToken(true, ytAccessToken); }
      },
      // 팝업을 닫거나(popup_closed) 팝업이 아예 안 뜨면(popup_failed_to_open) GIS는 callback이
      // 아니라 이쪽으로 알린다. 이걸 안 달면 약속이 영영 결착되지 않아 버튼이 잠긴 채 멈춘다
      // — 인증 심사 중인 앱에서 비테스트 계정은 '차단' 화면을 닫는 것 외엔 할 게 없으므로
      // 사실상 모든 일반 사용자가 그 상태에 빠졌다.
      error_callback: (err) => settleToken(false, new Error((err && err.type) || "popup_error")),
    });
  }
  return ytTokenClient;
}

function ensureYouTubeToken({ forcePrompt = false } = {}) {
  if (ytAccessToken && !forcePrompt) return Promise.resolve(ytAccessToken);
  return new Promise((resolve, reject) => {
    settleToken(false, new Error("superseded")); // 이전 요청이 남아 있으면 먼저 정리
    ytTokenPending = { resolve, reject };
    getYouTubeTokenClient().requestAccessToken({ prompt: forcePrompt ? "consent" : "" });
  });
}

async function createYouTubePlaylist(token, title) {
  const res = await fetch("https://www.googleapis.com/youtube/v3/playlists?part=snippet,status", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      snippet: { title, description: "Bandori Playlist Maker에서 생성됨" },
      status: { privacyStatus: "unlisted" },
    }),
  });
  if (!res.ok) {
    const err = new Error(`playlists.insert failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  return data.id;
}

async function addVideoToPlaylist(token, playlistId, videoId, position) {
  const res = await fetch("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      snippet: { playlistId, position, resourceId: { kind: "youtube#video", videoId } },
    }),
  });
  if (!res.ok) throw new Error(`playlistItems.insert failed: ${res.status}`);
}

// YouTube Data API v3에 배치 삽입 엔드포인트가 없어(HTTP batch는 2020년경 지원 종료) 순차 호출한다.
// 병렬 호출은 할당량을 더 빨리 태우고 순서 보장이 깨질 수 있어 피한다.
async function addAllVideosToPlaylist(token, playlistId, picksToAdd, onProgress) {
  const succeeded = [];
  const failed = [];
  for (let i = 0; i < picksToAdd.length; i++) {
    const p = picksToAdd[i];
    try {
      await addVideoToPlaylist(token, playlistId, p.video_id, i);
      succeeded.push(p.video_id);
    } catch (e) {
      failed.push({ video_id: p.video_id, error: String(e) });
    }
    onProgress(i + 1, picksToAdd.length);
  }
  return { succeeded, failed };
}

function setYtSaveStatus(text) {
  ytSaveStatusEl.textContent = text;
  show(ytSaveStatusEl);
}

function setYtProgress(n, total) {
  ytSaveProgressBarEl.style.width = `${Math.round((n / total) * 100)}%`;
  show(ytSaveProgressEl);
}

function hideYtProgress() {
  hide(ytSaveProgressEl);
  ytSaveProgressBarEl.style.width = "0%";
}

// 결과(또는 폴백) 열기 링크를 띄운다. window.open도 함께 시도하지만, OAuth 팝업이 닫힌 뒤라
// 사용자 제스처가 끊겨 팝업 차단에 막히는 경우가 많고 noopener면 성공 여부도 알 수 없다
// → 눌러서 확실히 열 수 있는 링크를 항상 함께 제공한다.
function offerYtOpenLink(url, label) {
  ytOpenLinkEl.href = url;
  ytOpenLinkEl.textContent = label;
  show(ytOpenLinkEl);
  window.open(url, "_blank", "noopener");
}

// 내 계정 저장이 불가능한 예외 상황(인증 심사 중 계정 차단·할당량 소진 등)의 폴백 —
// 이 기능 도입 전의 동작인 익명 watch_videos 임시 재생목록(YouTube에 'Untitled List'로 표시)으로
// 되돌린다. picks/재생 상태는 건드리지 않는다.
function openAnonymousPlaylistFallback(reason) {
  setYtSaveStatus(`${reason} 대신 임시 재생목록으로 들을 수 있어요(내 계정에는 저장되지 않아요).`);
  offerYtOpenLink(shareUrl, "임시 재생목록으로 열기 ↗");
  track("playlist_save_fallback_anonymous", { count: picks.length });
}

async function saveToYouTubePlaylist() {
  if (!picks.length || ytSaving) return;
  const btn = $("share-open");
  ytSaving = true;
  btn.disabled = true;
  hideYtProgress();
  hide(ytOpenLinkEl);
  setYtSaveStatus("Google 로그인 확인 중...");

  try {
    let token;
    try {
      token = await ensureYouTubeToken();
    } catch (e) {
      // 로그인 취소·팝업 닫힘, 그리고 인증(verification) 심사 중이라 계정이 차단된 경우가 모두 여기로 온다.
      track("playlist_save_auth_failed", { count: picks.length, reason: String((e && e.message) || e) });
      openAnonymousPlaylistFallback("Google 계정에 저장하지 못했어요.");
      return; // picks/재생 상태 불변
    }

    setYtSaveStatus("재생목록 만드는 중...");
    const title = (lastParams && lastParams.interpretation_summary)
      || `뱅드림 세트리스트 (${new Date().toISOString().slice(0, 10)})`;
    let playlistId;
    try {
      playlistId = await createYouTubePlaylist(token, title);
    } catch (e) {
      if (e.status === 401) {
        try {
          token = await ensureYouTubeToken({ forcePrompt: true });
          playlistId = await createYouTubePlaylist(token, title);
        } catch (_2) {
          playlistId = null;
        }
      }
      if (!playlistId) {
        track("playlist_save_create_failed", { count: picks.length });
        openAnonymousPlaylistFallback("재생목록을 만들지 못했어요.");
        return;
      }
    }

    const { succeeded, failed } = await addAllVideosToPlaylist(token, playlistId, picks, (n, total) => {
      setYtSaveStatus(`곡 추가 중... (${n}/${total})`);
      setYtProgress(n, total);
    });
    hideYtProgress();

    const playlistUrl = `https://www.youtube.com/playlist?list=${playlistId}`;
    if (failed.length === 0) {
      setYtSaveStatus("내 계정에 저장했어요 ✓");
      offerYtOpenLink(playlistUrl, "내 재생목록 열기 ↗");
    } else if (succeeded.length > 0) {
      setYtSaveStatus(`${picks.length}곡 중 ${succeeded.length}곡만 추가됐어요. 나머지는 YouTube에서 직접 추가해주세요.`);
      offerYtOpenLink(playlistUrl, "내 재생목록 열기 ↗");
    } else {
      openAnonymousPlaylistFallback("곡을 추가하지 못했어요.");
      return;
    }
    track("playlist_saved_to_account", { count: picks.length, succeeded: succeeded.length, failed: failed.length });
  } finally {
    // 어떤 경로로 빠져나가든 버튼은 반드시 되살린다(예외가 나도 잠기지 않게).
    ytSaving = false;
    btn.disabled = false;
    hideYtProgress();
  }
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
  link.textContent = "YouTube에서 열기 ↗";
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
  playbarPlayBtn.setAttribute("aria-label", isPlaying ? "일시정지" : "재생");
  playbarPlayBtn.title = isPlaying ? "일시정지" : "재생";
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
    playbarRepeatBtn.setAttribute("aria-label", "한 곡 반복 켜기");
    playbarRepeatBtn.title = "반복 (꺼짐)";
  } else if (repeatMode === "one") {
    playbarRepeatBtn.dataset.repeatLabel = "1";
    playbarRepeatBtn.setAttribute("aria-label", "전체 반복으로 전환");
    playbarRepeatBtn.title = "한 곡 반복 (켜짐)";
  } else {
    playbarRepeatBtn.dataset.repeatLabel = "A";
    playbarRepeatBtn.setAttribute("aria-label", "반복 끄기");
    playbarRepeatBtn.title = "전체 반복 (켜짐)";
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

function prettyBand(band) {
  return String(band).replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
// Camelot 코드 → 화성 코드(음이름 + 장/단조) 표기. src/scripts/data/camelot.py의
// KEY_TO_CAMELOT을 역매핑한 표(사용자에게 생소한 Camelot 대신 익숙한 조성명으로 노출).
const CAMELOT_TO_KEY_LABEL = {
  "1B": "B", "1A": "G♯m",
  "2B": "F♯", "2A": "D♯m",
  "3B": "C♯", "3A": "A♯m",
  "4B": "G♯", "4A": "Fm",
  "5B": "D♯", "5A": "Cm",
  "6B": "A♯", "6A": "Gm",
  "7B": "F", "7A": "Dm",
  "8B": "C", "8A": "Am",
  "9B": "G", "9A": "Em",
  "10B": "D", "10A": "Bm",
  "11B": "A", "11A": "F♯m",
  "12B": "E", "12A": "C♯m",
};
function keyLabel(camelot) {
  return CAMELOT_TO_KEY_LABEL[camelot] || camelot;
}
// 트랙 리스트의 곡별 파라미터 태그 — 6개 오디오 지표(PARAM_DEFS + 밝기)를 짧은 배지로.
const PICK_PARAM_DEFS = [
  { key: "valence", label: "밝기" },
  { key: "lufs_integrated", label: "라우드" },
  { key: "lra", label: "다이내믹" },
  { key: "danceability_norm", label: "리듬감" },
  { key: "instr_stem_ratio", label: "악기" },
  { key: "speech_median", label: "음절" },
];
// 곡별 파라미터 배지 — 예전 에너지 배지(미니 바 + 숫자)와 동일한 표현, 라벨만 앞에 붙인다.
function makeParamBadge(label, value) {
  const b = document.createElement("span");
  b.className = "badge badge-param";
  const lb = document.createElement("span");
  lb.className = "label";
  lb.textContent = label;
  const track = document.createElement("span");
  track.className = "bar-track";
  const fill = document.createElement("span");
  fill.className = "bar-fill";
  fill.style.width = `${Math.round(clamp01(value) * 100)}%`;
  track.appendChild(fill);
  const num = document.createElement("span");
  num.className = "num";
  num.textContent = String(Math.round(clamp01(value) * 100));
  b.append(lb, track, num);
  return b;
}
function harmonicLabelKo(h) {
  return { seed: "시작곡", same: "동일조성", adjacent: "하모닉인접", non_harmonic: "조성전환", added: "추가한 곡" }[h] || h;
}
function harmonicTooltipKo(h) {
  return {
    seed: "세트리스트의 첫 곡이라 직전 곡과 비교할 조성이 없어요.",
    same: "직전 곡과 조성이 완전히 같아요. 조옮김 없이 그대로 이어져 가장 매끄러운 전환이에요.",
    adjacent: "직전 곡과 Camelot Wheel 기준으로 인접한 조성이에요(관계조 또는 5도 이웃). 공통음이 많아 자연스럽게 넘어가요.",
    non_harmonic: "직전 곡과 조성이 같지도, 인접하지도 않아요. 곡 경계에서 조성이 크게 바뀌는 전환이에요.",
    added: "직접 추가한 곡이라 하모닉 배치 로직이 적용되지 않았어요.",
  }[h] || "";
}
function fmtNum(v) { return (typeof v === "number" ? v : 0).toFixed(2); }
function fmtSigned(v) { const n = typeof v === "number" ? v : 0; return (n >= 0 ? "+" : "") + n.toFixed(2); }

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function toggle(el, on) { el.classList.toggle("hidden", !on); }
