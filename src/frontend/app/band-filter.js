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

// 사용자가 '직접' 체크한 밴드만 요청 간 지속한다. 프롬프트 자동감지 밴드는 매 요청 일회성이어야
// 하므로(자연어 요청 = 매번 새 의도), 체크박스의 시각 상태와 분리해 별도 집합으로 추적한다.
// 이 집합은 오직 사용자의 change 이벤트로만 갱신 — 프로그램적 .checked 대입은 change를 발생시키지
// 않으므로 syncBandChecks가 여기 섞이지 않는다(요청 간 밴드 누적 버그의 근본 차단).
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

async function loadBands() {
  try {
    const res = await fetch(`${API_BASE}/api/bands`);
    const data = await res.json();
    cachedBands = data.bands || [];
    renderBands(cachedBands);
    // 구간별 밴드 셀렉터는 이 응답이 오기 전에 이미 그려졌을 수 있어(비동기), 도착 즉시 갱신.
    if (stageModel) renderStageGraph();
  } catch (_) {
    bandListEl.textContent = "밴드 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).";
  }
}

function renderBands(bands) {
  bandListEl.replaceChildren();
  if (!bands.length) { bandListEl.textContent = "밴드 없음"; return; }
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
    // 사용자가 직접 토글한 것만 manualBands에 반영(요청 간 지속 대상). syncBandChecks의
    // 프로그램적 대입은 change를 발생시키지 않으므로 자동감지분은 여기 들어오지 않는다.
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
  // 수동 선택분만 요청에 싣는다. 프롬프트 자동감지 밴드는 백엔드가 이번 프롬프트에서 매번 새로
  // 더하므로 프론트가 재전송하면 안 된다(이전 요청 밴드 누적 방지).
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

