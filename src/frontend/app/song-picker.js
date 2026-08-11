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

// isCoverSong/makeBandIcon은 app/utils.js 참조.

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

