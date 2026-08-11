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
    showError(t("edit.allRemoved"));
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

