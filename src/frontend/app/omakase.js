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

