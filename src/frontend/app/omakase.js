// ── 오마카세(시간대+날씨 기반 프롬프트 자동 생성) ──────────────────────────────────
// 문구 뱅크는 app/i18n.js(omakase.time.*/omakase.weather.*/omakase.suffixes)에 언어별로
// 있다 — 여기서는 getter로 항상 현재 언어의 배열을 읽는다(고정 배열로 캐시하지 않음).
const OMAKASE_TIME_PHRASES = {
  get dawn() { return tArr("omakase.time.dawn"); },
  get morning() { return tArr("omakase.time.morning"); },
  get afternoon() { return tArr("omakase.time.afternoon"); },
  get evening() { return tArr("omakase.time.evening"); },
  get night() { return tArr("omakase.time.night"); },
};
const OMAKASE_WEATHER_PHRASES = {
  get clear() { return tArr("omakase.weather.clear"); },
  get cloudy() { return tArr("omakase.weather.cloudy"); },
  get rain() { return tArr("omakase.weather.rain"); },
  get snow() { return tArr("omakase.weather.snow"); },
  get storm() { return tArr("omakase.weather.storm"); },
};
function omakaseSuffixes() { return tArr("omakase.suffixes"); }

// "밤(night)"·"새벽(dawn)"엔 해가 없어 "햇살 좋은" 같은 낮 전용 표현이 말이 안 된다("햇살 좋은
// 날씨에 어울리는 늦은 밤 감성적인 플리" 버그 리포트) — 그 시간대에는 clearDaytime 문구를
// 풀에서 아예 뺀다. 다른 날씨(비/눈/폭풍/흐림) 문구는 시간대 특정 표현이 없어 그대로 둔다.
const OMAKASE_DAYTIME_PERIODS = new Set(["morning", "afternoon", "evening"]);
function omakaseWeatherPool(weather, timeOfDay) {
  const base = OMAKASE_WEATHER_PHRASES[weather] || [];
  if (weather === "clear" && OMAKASE_DAYTIME_PERIODS.has(timeOfDay)) {
    return [...base, ...tArr("omakase.weather.clearDaytime")];
  }
  return base;
}

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
  if (ctx.weather) {
    const pool = omakaseWeatherPool(ctx.weather, ctx.timeOfDay);
    if (pool.length) parts.push(pickRandom(pool));
  }
  parts.push(pickRandom(OMAKASE_TIME_PHRASES[ctx.timeOfDay]));
  parts.push(pickRandom(omakaseSuffixes()));
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
    promptEl.placeholder = t("omakase.generating");
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

