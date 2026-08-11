"use strict";

// ── DOM ──────────────────────────────────────────────────────────────────────
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

// ── 언어 선택 ─────────────────────────────────────────────────────────────────
// 번역 문자열·전환 로직 자체는 app/i18n.js(항상 첫 번째로 로드) 담당 — 여기서는 버튼·팝업
// UI만 다루고 실제 언어 전환은 i18n.setLang()에 위임한다.
const langToggleBtn = $("lang-toggle");
const langPopupEl = $("lang-popup");
if (langToggleBtn && langPopupEl) {
  const closeLangPopup = () => {
    langPopupEl.hidden = true;
    langToggleBtn.setAttribute("aria-expanded", "false");
  };
  const syncLangUi = () => {
    const lang = window.i18n.getLang();
    langPopupEl.querySelectorAll(".lang-option").forEach((el) => {
      const active = el.dataset.lang === lang;
      el.classList.toggle("is-active", active);
      el.setAttribute("aria-checked", String(active));
      if (active) langToggleBtn.textContent = el.dataset.code;
    });
  };
  langToggleBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = langPopupEl.hidden;
    langPopupEl.hidden = !willOpen;
    langToggleBtn.setAttribute("aria-expanded", String(willOpen));
  });
  langPopupEl.querySelectorAll(".lang-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      window.i18n.setLang(btn.dataset.lang);
      track("lang_select", { lang: btn.dataset.lang });
      closeLangPopup();
    });
  });
  document.addEventListener("click", (e) => {
    if (!langPopupEl.hidden && !langPopupEl.contains(e.target) && e.target !== langToggleBtn) {
      closeLangPopup();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !langPopupEl.hidden) closeLangPopup();
  });
  syncLangUi();
  document.addEventListener("i18n:change", syncLangUi);
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

// 백엔드도 500자 하드캡을 두지만(schemas.py), 여기서는 프론트에서 먼저 입력을 막고
// 한계에 닿았을 때만 안내한다(native maxlength라 501번째 글자부터는 조용히 씹혀서 이유를 알기 어려움).
promptEl.addEventListener("input", () => {
  if (promptEl.value.length >= promptEl.maxLength) {
    promptHintEl.textContent = t("form.promptMaxLen", { n: promptEl.maxLength });
    promptHintEl.classList.add("notice");
  } else {
    promptHintEl.textContent = "";
    promptHintEl.classList.remove("notice");
  }
});

