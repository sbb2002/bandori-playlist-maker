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
    showError(t("error.noMatch"));
    return;
  }

  lastParams = data.params || {};
  lastAppliedBands = data.applied_bands || [];
  lastEstimatedTotalSeconds = estimatedTotal;
  // data.params.stage_minutes는 LLM의 '의도'일 뿐, 실제 적용 결과(완충 노드로 슬롯이 건너뛰어질
  // 수 있음 등)와 다를 수 있다 — 그래서 width는 여기서 실제 곡 배정 결과(picks의 stage_index별
  // 개수)로 직접 계산한다. 이렇게 안 하면 커스텀 모드 프리필(prefillCustomFromLast)이 항상
  // 균등폭(1/n)으로 되돌아가 "마지막 구간만 길게" 같은 요청이 커스텀 모드로 넘어오면서 사라져
  // 보인다(실사용 버그로 발견). stage_minutes 자체는 디버그 스냅샷(last_ai_params)에서 확인 가능.
  // count가 0인 스테이지(곡이 배정되지 않은 스테이지 — 예: flexible_duration으로 세트리스트가
  // 조기 종료돼 뒤쪽 스테이지가 통째로 비는 경우)도 width를 명시적으로 0으로 채운다. 예전엔
  // count>0일 때만 width를 넣고 나머지는 undefined로 남겨뒀는데, stage-graph.js의
  // syncGraphToParams가 undefined를 1/n으로 대체하면서 이미 합이 1인 나머지 스테이지 width에
  // 얹혀 그래프가 오른쪽으로 삐져나가는 버그가 있었다(2026-08-14 실사용 발견).
  lastStages = (data.stages || []).map((s, i) => {
    const count = picks.filter((p) => p.stage_index === i).length;
    return { ...s, width: count / picks.length };
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
  // 그래프 X축·재생시간 입력창은 LLM의 "목표"(params.target_minutes)가 아니라 이 결과가
  // 실제로 몇 분짜리인지(estimatedTotal)를 보여준다 — flexible_duration(AI 모드, 재생시간
  // 미지정 요청)으로 실제 곡 수가 목표보다 짧게 끝날 수 있어, 목표치를 그대로 쓰면 그래프
  // X축 끝(0~목표분)이 실제 플레이리스트 길이와 안 맞았다(2026-08-15 실사용 피드백).
  const actualMinutes = Math.round(estimatedTotal / 60);
  if (!minutesTouched && actualMinutes > 0) {
    $("target-minutes").value = actualMinutes;
    if (stageModel) { stageModel.totalMinutes = actualMinutes; }
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
  interp.textContent = p.interpretation_summary || t("summary.defaultInterp");
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
  for (const c of [t("summary.songCount", { n: picks.length }), t("summary.approxMinutes", { n: mins })]) {
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
    badges.appendChild(makeBadge("key", keyLabel(p.camelot), t("track.keyTooltip", { code: p.camelot || "" })));
    // 후보 풀 부족으로 목표 무드에서 다소 벗어난 채 채워진 곡 — 버그가 아니라 catalog 한계임을
    // 사용자에게 투명하게 알리는 배지(2026-08-14, 실사용 피드백: 태그 없이는 "왜 이 곡이?"로
    // 오인되기 쉬움).
    if (p.reason && p.reason.degraded) {
      badges.appendChild(makeBadge("degraded", t("track.degradedLabel"), t("track.degradedTooltip")));
    }
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

// 언어 전환 시 이미 화면에 떠 있는 결과(요약·배지·트랙리스트)를 새 언어로 다시 그린다.
// picks/lastParams는 이미 생성된 결과 그대로이므로 재요청 없이 로컬 재렌더만으로 충분하다.
document.addEventListener("i18n:change", () => {
  if (!picks.length) return;
  renderSummary({ params: lastParams });
  renderTracklist(picks);
});

