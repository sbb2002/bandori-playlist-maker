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

