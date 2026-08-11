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

