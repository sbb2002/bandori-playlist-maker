/* setlist-maker 프론트 — 요청 → 세트리스트 렌더 → YouTube 순차 자동재생 + umami 계측.
 * 백엔드 계약: architecture.md 스키마3 (POST /api/setlist, GET /api/health, 공통 에러 포맷).
 *
 * app/*.js 로드 순서 안내: 이 파일이 항상 첫 번째로 로드된다. 아래 정의는 다른 어떤 모듈에도
 * 의존하지 않는 leaf 헬퍼/상수만 모아둔 것 — index.html이 나머지 스크립트를 <script> 태그
 * 순서대로(모듈 아님, 전역 스코프 공유) 로드하므로, 여기서 정의한 함수는 아무 시점에(다른
 * 모듈의 최상위 동기 코드에서도) 안전하게 호출할 수 있다. 새 leaf 헬퍼를 추가할 때도 이
 * 규칙(다른 app/*.js를 참조하지 않음)을 지킬 것 — 안 지키면 script 태그 순서에 따라
 * ReferenceError가 날 수 있다(BAND_ORDER가 실사용 중 이 문제로 깨졌던 전례가 있음).
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

const $ = (id) => document.getElementById(id);

// ── umami 계측(스크립트 미설치 시 무해) ─────────────────────────────────────────
function track(name, data) {
  try {
    if (window.umami && typeof window.umami.track === "function") window.umami.track(name, data);
  } catch (_) {/* 계측 실패는 UX에 영향 주지 않음 */}
}

// 범용 유틸(트랙리스트·프리셋·플레이바 등 여러 곳에서 공유) — 2D 정서 지도 이식 과정에서
// 실수로 함께 지워졌던 것을 복원(elDiv/clamp 누락으로 결과 렌더링·재생바가 ReferenceError로 깨졌음).
function elDiv(cls) { const d = document.createElement("div"); d.className = cls; return d; }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
const clamp01 = (v) => Math.max(0, Math.min(1, v));

const SVG_NS = "http://www.w3.org/2000/svg";

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }
function toggle(el, on) { el.classList.toggle("hidden", !on); }

// bandori-song-sorter와 동일한 밴드 나열 순서(아이콘 애셋은 assets/bands/<band>.png, 미포함은
// 뒤). renderStageGraph()가 페이지 로드 시 동기적으로 한 번 실행되며 구간별 밴드 셀렉터를
// 채우려고 이 함수를 곧바로 호출하므로, utils.js(항상 첫 번째로 로드)에 둬야 한다 — 다른
// app/*.js 파일에 있으면 script 태그 로드 순서에 따라 TDZ/ReferenceError가 난다(실사용 버그로
// 발견된 전례가 있어 분리 시에도 이 파일에 유지).
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
// label은 함수로 둬서(고정 문자열 아님) 언어 전환 후 다시 그릴 때도 최신 번역을 읽는다.
const PICK_PARAM_DEFS = [
  { key: "valence", get label() { return t("paramShort.valence"); } },
  { key: "lufs_integrated", get label() { return t("paramShort.lufs"); } },
  { key: "lra", get label() { return t("paramShort.lra"); } },
  { key: "danceability_norm", get label() { return t("paramShort.dance"); } },
  { key: "instr_stem_ratio", get label() { return t("paramShort.instr"); } },
  { key: "speech_median", get label() { return t("paramShort.speech"); } },
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
  return t(`harmonic.${h}.label`) !== `harmonic.${h}.label` ? t(`harmonic.${h}.label`) : h;
}
function harmonicTooltipKo(h) {
  const key = `harmonic.${h}.tooltip`;
  const val = t(key);
  return val !== key ? val : "";
}
function fmtNum(v) { return (typeof v === "number" ? v : 0).toFixed(2); }
function fmtSigned(v) { const n = typeof v === "number" ? v : 0; return (n >= 0 ? "+" : "") + n.toFixed(2); }
