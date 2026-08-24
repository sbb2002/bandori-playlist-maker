// ── 설정: 밴드 필터 · 단계 직접 지정 (§5-1) ────────────────────────────────────
const bandListEl = $("band-list");
const mapPadEl = $("map-pad");
const mapSvgEl = $("map-svg");
const timebarEl = $("timebar");
const timebarTicksEl = $("timebar-ticks");
const timebarTotalLabelEl = $("timebar-total-label");
const impressionRowEl = $("impression-row");
const stageNEl = $("stage-n");
const paramGraphsEl = $("param-graphs");
const bgToggleEl = $("bg-toggle");
const stagePlusBtn = $("stage-plus");
const stageMinusBtn = $("stage-minus");
let stageTouched = false; // 사용자가 그래프를 조정했는지 — 조정 전엔 LLM 에너지 자동 사용
// 사용자가 직접 건드린 설정만 요청에 override로 싣는다. 안 건드린 값은 생략 → LLM이 결정하고,
// 응답 후 그 값을 UI에 '반영'만 한다(다음 요청에 강제되지 않게 — 밴드 필터 패턴과 동일).
let minutesTouched = false;
let coverTouched = false;
let settingsType = "all"; // "all" | "original" | "cover" — 세 개 중 항상 정확히 하나만 켜짐(토글 버튼)

// 실제 요청에 실리는 밴드 필터 상태. 사용자의 change 이벤트로 갱신되며, syncBandChecks(playbar.js)도
// 프롬프트 자동감지분을 여기 편입시킨다 — 체크박스에 보이는 상태 = 이 집합이 항상 같아야 사용자가
// 화면에서 본 대로 다음 재생성에도 유지된다(2026-08-24, 어긋나서 생긴 버그 수정).
const manualBands = new Set();
// 감성 설정 구간별 밴드 셀렉터(#impression-row) 옵션 채우기용 — loadBands()가 채운다.
let cachedBands = [];

// 구간별 "밴드 고정" 팝업 상태 — buildImpressionRow()가 매 렌더마다 다시 채우지만, 열림
// 상태 추적과 바깥 클릭 감지는 재렌더에도 살아남아야 해서 최상위(모듈 스코프)에 둔다.
let impressionBandToggleEls = [];
let impressionBandPopupEls = [];
let openBandPopupIndex = -1;

function closeBandPopup() {
  if (openBandPopupIndex !== -1 && impressionBandPopupEls[openBandPopupIndex]) {
    impressionBandPopupEls[openBandPopupIndex].classList.add("hidden");
  }
  openBandPopupIndex = -1;
}
document.addEventListener("click", (e) => {
  if (openBandPopupIndex === -1) return;
  const popup = impressionBandPopupEls[openBandPopupIndex];
  const toggle = impressionBandToggleEls[openBandPopupIndex];
  if (popup && !popup.contains(e.target) && toggle && !toggle.contains(e.target)) {
    closeBandPopup();
  }
});

// 구간별 밴드 고정 팝업에 보여줄 밴드 목록 — 전역 밴드 필터에서 수동 선택한 것이 있으면
// 그것만, 없으면(=전체) 전체 밴드. "전역에서 선택한 모든 밴드"라는 사용자 요구사항 그대로.
function effectiveGlobalBandChoices() {
  const present = manualBands.size > 0 ? [...manualBands] : cachedBands.map((b) => b.band);
  return bandsInSelectorOrder(present);
}

// 구간별 밴드 고정 팝업 내용 채우기 — 전역 밴드 필터와 동일한 디자인(.band-list/.band-item)
// 재사용. 다중 선택(체크박스)이라 전역 필터와 달리 label에 이름을 병기하지 않고 아이콘+
// 곡수만(공간 절약, 툴팁으로 이름 확인) — 전역 밴드 필터와 동일한 관례.
function renderBandPopupOptions(popupEl, i) {
  popupEl.replaceChildren();
  const list = document.createElement("div");
  list.className = "band-list";
  const countByBand = new Map(cachedBands.map((b) => [b.band, b.count]));
  const seg = stageModel.segments[i];
  for (const band of effectiveGlobalBandChoices()) {
    const label = document.createElement("label");
    label.className = "band-item";
    label.title = prettyBand(band);
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "band-cb";
    cb.checked = (seg.bands || []).includes(band);
    cb.addEventListener("change", () => {
      stageTouched = true;
      const cur = new Set(stageModel.segments[i].bands || []);
      if (cb.checked) cur.add(band); else cur.delete(band);
      stageModel.segments[i].bands = [...cur];
      updateBandToggleIndicator(i);
    });
    const icon = makeBandIcon(band, "band-item-icon");
    const count = document.createElement("span");
    count.className = "band-item-count";
    count.textContent = countByBand.get(band) ?? "";
    label.append(cb, icon, count);
    list.appendChild(label);
  }
  popupEl.appendChild(list);
}

function updateBandToggleIndicator(i) {
  const btn = impressionBandToggleEls[i];
  if (!btn || !stageModel.segments[i]) return;
  btn.classList.toggle("on", (stageModel.segments[i].bands || []).length > 0);
}

// BAND_ORDER/bandsInSelectorOrder는 app/utils.js 참조(항상 첫 번째로 로드되어 이 함수 안에서
// 안전하게 쓸 수 있음 — 자세한 이유는 그 파일 헤더 코멘트 참고).

// Render 백엔드가 cold start로 잠들어 있으면 첫 fetch가 (재시도 없이) 즉시 실패해 에러
// 문구에서 멈춘다 — 새로고침만 해결되는 이유는 새 페이지 로드가 새 fetch를 트리거해서일
// 뿐, 그사이 백엔드가 깨어난 것과는 무관하다. cold start 각성 시간(약 30~50초)을 커버하는
// 백오프 재시도로 새로고침 없이도 자연스럽게 회복하게 한다.
async function loadBands(attempt = 0) {
  try {
    const res = await fetch(`${API_BASE}/api/bands`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    cachedBands = data.bands || [];
    renderBands(cachedBands);
    // 구간별 밴드 셀렉터는 이 응답이 오기 전에 이미 그려졌을 수 있어(비동기), 도착 즉시 갱신.
    if (stageModel) renderStageGraph();
  } catch (_) {
    if (attempt < 6) {
      setTimeout(() => loadBands(attempt + 1), 3000 * (attempt + 1));
    } else {
      bandListEl.classList.remove("band-list-loading");
      bandListEl.textContent = t("options.bandLoadError");
    }
  }
}

function renderBands(bands) {
  bandListEl.classList.remove("band-list-loading");
  bandListEl.replaceChildren();
  if (!bands.length) { bandListEl.textContent = t("options.bandNone"); return; }
  // 표처럼 가지런한 그리드: 밴드 아이콘 + 곡 수(이름 생략, 툴팁으로 제공). 순서=BAND_ORDER.
  const countByBand = new Map(bands.map((b) => [b.band, b.count]));
  for (const band of bandsInSelectorOrder([...countByBand.keys()])) {
    const label = document.createElement("label");
    label.className = "band-item";
    label.title = prettyBand(band); // 이름은 툴팁으로
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.value = band;
    cb.className = "band-cb";
    cb.addEventListener("change", () => {
      if (cb.checked) manualBands.add(cb.value);
      else manualBands.delete(cb.value);
      syncStageBandsToGlobalFilter();
    });
    const icon = makeBandIcon(band, "band-item-icon");
    const count = document.createElement("span");
    count.className = "band-item-count";
    count.textContent = countByBand.get(band);
    label.append(cb, icon, count);
    bandListEl.appendChild(label);
  }
}

function collectBands() {
  return [...manualBands];
}

$("band-clear").addEventListener("click", () => {
  manualBands.clear();
  document.querySelectorAll(".band-cb:checked").forEach((c) => (c.checked = false));
  syncStageBandsToGlobalFilter();
});

// 전역 밴드 필터가 바뀌면(체크·해제·전체 해제) 구간별 "밴드 고정" 선택도 즉시 반영한다
// (사용자 요구사항) — 더 이상 전역에서 유효하지 않은 구간별 선택은 정리하고, 열려 있는
// 팝업이 있으면 새 옵션으로 다시 그린다.
function syncStageBandsToGlobalFilter() {
  if (!stageModel) return;
  const allowed = new Set(effectiveGlobalBandChoices());
  stageModel.segments.forEach((s, i) => {
    if (s.bands && s.bands.length) {
      s.bands = s.bands.filter((b) => allowed.has(b));
    }
    updateBandToggleIndicator(i);
  });
  if (openBandPopupIndex !== -1 && impressionBandPopupEls[openBandPopupIndex]) {
    renderBandPopupOptions(impressionBandPopupEls[openBandPopupIndex], openBandPopupIndex);
  }
}

// 언어 전환 시 세부 설정 그래프 전체(구간 수·"밴드 고정"·placeholder 예시 등 번역 문자열이
// 섞인 동적 UI)를 다시 그린다. renderStageGraph()는 매번 통째로 재구성하므로 재호출만으로 충분.
document.addEventListener("i18n:change", () => {
  if (stageModel) renderStageGraph();
});

