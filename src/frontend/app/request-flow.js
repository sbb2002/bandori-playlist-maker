// ── 요청 ─────────────────────────────────────────────────────────────────────
form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const body = {};

  if (currentMode === "ai") {
    // ── AI 모드: 프롬프트 필수 ──
    const prompt = $("prompt").value.trim();
    if (!prompt) return;
    body.prompt = prompt;
    body.mode = "ai";
    // 백엔드가 interpretation_summary·tags·구간별 impression을 이 언어로 쓰도록 지시하는 데
    // 씀(app/i18n.js currentLang과 동일 값 — backend/app/api/schemas.py SetlistRequest.lang).
    body.lang = window.i18n.getLang();

    if (minutesTouched) {
      const minutes = parseInt($("target-minutes").value, 10);
      if (!Number.isNaN(minutes)) body.target_minutes = minutes;
    }

    const bands = collectBands();
    if (bands.length) body.bands = bands;
    const customStages = collectStages();
    if (customStages) body.stages = customStages;
    if (coverTouched) {
      Object.assign(body, typeToFlags(settingsType));
    }
  } else {
    // ── 커스텀 모드: 직접 구성한 stages 전송 ──
    body.mode = "custom";
    const customStages = collectStagesForCustomMode();
    if (!customStages || customStages.length === 0) {
      showError(t("error.needStages"));
      return;
    }
    body.stages = customStages;

    if (minutesTouched) {
      const minutes = parseInt($("target-minutes").value, 10);
      if (!Number.isNaN(minutes)) body.target_minutes = minutes;
    }

    const bands = collectBands();
    if (bands.length) body.bands = bands;
    if (coverTouched) {
      Object.assign(body, typeToFlags(settingsType));
    }
  }

  showLoading(true);
  hide(errorEl);
  hide(resultEl);

  try {
    const res = await fetch(`${API_BASE}/api/setlist`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let data = await res.json().catch(() => null);
    if (res.status === 202) {
      // 큐잉(TPM 페이싱) 중 — job_id로 폴링해서 완료를 기다린다(architecture.md 스키마3 확장).
      data = await pollSetlistJob(data);
    } else if (!res.ok) {
      const msg = (data && data.error && data.error.message) || t("error.requestFailed", { status: res.status });
      throw new Error(msg);
    }
    renderResult(data);
    // lastStages(width 포함)는 renderResult가 이미 채워둔다 — 여기서 다시 덮어쓰면
    // width 계산이 유실된다(재도입 금지).
  } catch (err) {
    const offline = err instanceof TypeError;
    showError(offline
      ? t("error.backendDown")
      : err.message);
  } finally {
    showLoading(false);
  }
});

// 큐 대기(TPM 페이싱) 폴링 — POST /api/setlist가 202+job_id를 주면(트래픽 몰려 리미터가
// 요청을 바로 못 받는 경우) GET .../status/{job_id}를 주기적으로 물어 완료를 기다린다.
// 예전엔 서버가 이 대기를 HTTP 요청 안에서 블로킹하다 20초 넘으면 그냥 429를 냈는데(사용자 피드백:
// "큐 대기 중인데 단순히 20초 넘어갔다고 429 처리하면 안 되지"), 이제 대기 자체는 서버 백그라운드
// 잡으로 옮기고 여기서 폴링하며 "몇 초 남음"을 계속 갱신해 보여준다.
const SETLIST_POLL_INTERVAL_MS = 1500;
const SETLIST_POLL_TIMEOUT_MS = 5 * 60 * 1000; // 5분 — groq_adapter.py tpm_max_wait(180s)보다 여유

function setQueueWaitMessage(waitSeconds, queuePosition) {
  if (!loadingSubEl) return;
  const ahead = queuePosition > 0 ? t("queue.ahead", { n: queuePosition }) : "";
  if (waitSeconds == null || waitSeconds <= 0) {
    loadingSubEl.textContent = ahead
      ? t("queue.soonWithAhead", { ahead })
      : t("queue.wrappingUp");
    return;
  }
  const rounded = Math.max(1, Math.round(waitSeconds));
  loadingSubEl.textContent = t("queue.eta", { ahead, sec: rounded });
}

async function pollSetlistJob(initial) {
  const jobId = initial && initial.job_id;
  if (!jobId) throw new Error(t("error.queueRegisterFail"));
  if (coldStartTimer) { clearTimeout(coldStartTimer); coldStartTimer = null; } // 콜드스타트 안내와 겹치지 않게
  setQueueWaitMessage(initial.estimated_wait_seconds, initial.queue_position);

  const deadline = Date.now() + SETLIST_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, SETLIST_POLL_INTERVAL_MS));
    const res = await fetch(`${API_BASE}/api/setlist/status/${jobId}`);
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = (data && data.error && data.error.message) || t("error.requestFailed", { status: res.status });
      throw new Error(msg);
    }
    if (data.status === "done") return data.result;
    setQueueWaitMessage(data.estimated_wait_seconds, data.queue_position);
  }
  throw new Error(t("error.queueTimeout"));
}

// 대기 UX(트래픽/콜드스타트 대비): 로딩 중 문구를 위트있게 순환하고, 오래 걸리면(콜드스타트 추정)
// '서버 깨우는 중' 안내로 강화. 무료 플랜 슬립 시 첫 응답이 느려도 이탈을 줄인다.
const loadingTextEl = loadingEl.querySelector(".loading-text");
const loadingSubEl = loadingEl.querySelector(".loading-sub");
let loadingRotateTimer = null;
let coldStartTimer = null;

// 세트리스트 생성 요청이 오가는 동안 AI 모드 프롬프트 입력창과 커스텀 모드 전체 파라미터를
// 잠근다 — 응답이 오기 전에 사용자가 값을 바꾸면, 화면(다음 요청에 실릴 값)과 방금 보낸
// 요청이 서로 다른 상태를 가리키는 레이스 컨디션이 생긴다.
function setFormLocked(locked) {
  promptEl.disabled = locked;
  if (omakaseBtn) omakaseBtn.disabled = locked;
  const modeSwitch = $("mode-switch");
  if (modeSwitch) modeSwitch.disabled = locked;
  const optionsDetails = $("options-details");
  if (optionsDetails) optionsDetails.classList.toggle("locked", locked);
}

function showLoading(on) {
  submitBtn.disabled = on;
  setFormLocked(on);
  toggle(loadingEl, on);
  if (on) startLoadingAnimation();
  else stopLoadingAnimation();
}

function startLoadingAnimation() {
  let i = 0;
  const messages = tArr("loading.messages");
  if (loadingTextEl) loadingTextEl.textContent = messages[0];
  if (loadingSubEl) loadingSubEl.textContent = t("loading.sub");
  loadingRotateTimer = setInterval(() => {
    i = (i + 1) % messages.length;
    if (loadingTextEl) loadingTextEl.textContent = messages[i];
  }, 2200);
  // 8초 넘게 걸리면 콜드스타트로 보고 위트 멘트로 안내 강화.
  coldStartTimer = setTimeout(() => {
    if (loadingSubEl) loadingSubEl.textContent = t("loading.coldstart");
  }, 8000);
}

function stopLoadingAnimation() {
  if (loadingRotateTimer) { clearInterval(loadingRotateTimer); loadingRotateTimer = null; }
  if (coldStartTimer) { clearTimeout(coldStartTimer); coldStartTimer = null; }
}
function showError(message) {
  errorEl.textContent = "⚠️ " + message;
  show(errorEl);
}

