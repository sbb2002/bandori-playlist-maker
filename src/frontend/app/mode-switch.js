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
  // 위젯이 실제로 쓸 totalMinutes를 먼저 확정한다(아래 stageModel.totalMinutes 대입과 같은
  // 우선순위 — lastParams.target_minutes가 있고 사용자가 안 건드렸으면 그 값, 아니면 기존
  // stageModel 값, 그것도 없으면 60).
  const effectiveTotalMinutes =
    !minutesTouched && lastParams && typeof lastParams.target_minutes === "number"
      ? lastParams.target_minutes
      : (stageModel ? stageModel.totalMinutes : 60);
  // width에 최소 하한을 두고 재정규화한다 — flexible_duration(AI 모드, 재생시간 미지정 요청)
  // 도입 이후 특정 스테이지가 곡을 0개 배정받는 경우가 생겼는데(품질 게이트가 그 스테이지
  // 진입 전에 멈춤), 그 스테이지의 width가 정확히 0이면 "구간 시간길이 정하기" 바에서 그
  // 구간의 경계 핸들이 옆 구간과 같은 위치(0% 또는 100%)에 겹쳐 그려져 트랙 밖으로 삐져나온
  // 것처럼 보이는 버그가 있었다(2026-08-15 실사용 발견). 최소 하한은 이 바가 이미 강제하는
  // "구간당 최소 3분"(MIN_WIDTH_MIN)과 동일 기준 — 그래야 하한을 적용해도 이후 사용자가
  // 드래그로 조정할 때의 최소폭 규칙과 어긋나지 않는다.
  const minFrac = MIN_WIDTH_MIN / effectiveTotalMinutes;
  const rawWidths = lastStages.map((s) => (s.width != null ? s.width : 1 / n));
  const flooredWidths = rawWidths.map((w) => Math.max(w, minFrac));
  const widthSum = flooredWidths.reduce((a, b) => a + b, 0);
  const normalizedWidths = flooredWidths.map((w) => w / widthSum);
  const mapped = lastStages.map((s, i) => ({
    width: normalizedWidths[i],
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
  // totalMinutes도 함께 복원(위 effectiveTotalMinutes와 동일 값) — 마지막으로 완료된 AI
  // 응답의 target_minutes가 있으면 그걸 쓴다. 예전엔 여기서 안 건드려서, AI 요청 응답이 오기
  // 전에 커스텀 모드로 전환하면(모드 탭 자체는 request-flow.js가 의도적으로 안 잠근다)
  // reflectSettings()가 아직 한 번도 안 돌아 stageModel.totalMinutes가 페이지 로드 시점
  // 기본값(target-minutes 입력창이 비어 60으로 폴백)에 그대로 머물러 있었다(2026-08-15
  // 실사용 발견).
  stageModel.totalMinutes = effectiveTotalMinutes;
  if (!minutesTouched) minutesEl.value = effectiveTotalMinutes;

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

