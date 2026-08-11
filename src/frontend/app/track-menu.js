// ── 트랙 우클릭·길게누름 메뉴("다음 곡 추가"/"현재 곡 제거") ─────────────────────
// attachGraphMenu(그래프 구간 메뉴)와 동일한 구조: pointerdown 시 타이머 예약 → 10px 초과
// 이동 시 취소 → 시간 초과 시 clamp된 위치에 메뉴 표시. bodyEl(제목 영역)에만 걸어 이동 핸들
// (track-move)·제거버튼(track-remove)·인서터(+)와는 겹치지 않는다. renderTracklist가 매 렌더마다
// 새 li/bodyEl을 만들므로(위 replaceChildren) 리스너가 누적되지 않는다.
let trackMenuEl = null;
let trackLongPressFired = false;

function closeTrackMenu() {
  if (trackMenuEl) { trackMenuEl.remove(); trackMenuEl = null; }
}

function openTrackMenu(clientX, clientY, items) {
  closeTrackMenu();
  const menu = elDiv("graph-menu"); // 기존 컨텍스트 메뉴 스타일 재사용
  for (const it of items) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "graph-menu-item";
    b.textContent = it.label;
    b.addEventListener("click", () => { closeTrackMenu(); it.onClick(); });
    menu.appendChild(b);
  }
  menu.style.visibility = "hidden"; // 측정 후 위치 보정
  document.body.appendChild(menu);
  const r = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(clientX, window.innerWidth - r.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(clientY, window.innerHeight - r.height - 8))}px`;
  menu.style.visibility = "";
  trackMenuEl = menu;
}

document.addEventListener("pointerdown", (e) => {
  if (trackMenuEl && !trackMenuEl.contains(e.target)) closeTrackMenu();
}, true);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeTrackMenu(); });
window.addEventListener("scroll", () => closeTrackMenu(), true);

let trackLpTimer = null;
let trackLpStartXY = null;
function clearTrackLongPress() { if (trackLpTimer) { clearTimeout(trackLpTimer); trackLpTimer = null; } trackLpStartXY = null; }
document.addEventListener("pointermove", (e) => {
  if (trackLpStartXY && Math.hypot(e.clientX - trackLpStartXY.x, e.clientY - trackLpStartXY.y) > 10) clearTrackLongPress();
}, true);
document.addEventListener("pointerup", clearTrackLongPress, true);
document.addEventListener("pointercancel", clearTrackLongPress, true);

function attachTrackLongPress(bodyEl, index) {
  const openFor = (clientX, clientY) => {
    openTrackMenu(clientX, clientY, [
      { label: "다음 곡 추가", onClick: () => openSongPickerAt(index + 1) },
      { label: "현재 곡 제거", onClick: () => removeSong(index) },
    ]);
  };
  bodyEl.addEventListener("contextmenu", (e) => { e.preventDefault(); openFor(e.clientX, e.clientY); });
  bodyEl.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "mouse") return; // 데스크톱은 contextmenu(우클릭) 사용
    trackLongPressFired = false; // 새 제스처 시작 — 이전 제스처의 잔여 플래그 정리
    const x = e.clientX, y = e.clientY;
    if (trackLpTimer) clearTimeout(trackLpTimer);
    trackLpStartXY = { x, y };
    trackLpTimer = setTimeout(() => {
      trackLpTimer = null;
      trackLongPressFired = true;
      openFor(x, y);
    }, LONGPRESS_MS);
  });
}

// 트랙 우측 액션 — 이동 핸들(상하 셰브런) · 제거(−). 행 호버 시 은은히 나타나는 고스트 버튼.
// 곡 추가(+)는 트랙 사이 인서터로 분리(makeInserter) — 더 직관적인 '사이 삽입'.
function makeTrackActions(li, index) {
  const actions = elDiv("track-actions");
  actions.addEventListener("click", (e) => e.stopPropagation()); // 행 클릭(재생) 방지

  const move = document.createElement("button");
  move.type = "button";
  move.className = "track-btn track-move";
  move.title = "잡고 위아래로 드래그해 순서 이동";
  move.setAttribute("aria-label", "순서 이동 (드래그)");
  move.innerHTML =
    '<svg viewBox="0 0 24 16" fill="none" stroke="currentColor" stroke-width="2.4" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M5 6.5 L12 1.5 L19 6.5"/><path d="M5 9.5 L12 14.5 L19 9.5"/></svg>';
  move.addEventListener("pointerdown", (e) => startReorder(move, li, e));

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "track-btn track-remove";
  remove.title = "이 곡 제거";
  remove.setAttribute("aria-label", "곡 제거");
  remove.innerHTML =
    '<svg viewBox="0 0 16 16" aria-hidden="true">' +
    '<rect x="3" y="7" width="10" height="2" rx="1" fill="currentColor"/></svg>';
  remove.addEventListener("click", () => removeSong(index));

  actions.append(move, remove);
  return actions;
}

// 트랙 사이 삽입점(+): 트랙 아래 간격에 겹쳐 두고, 그 구역에 호버하면 중앙에 '+'가 떠오른다.
// atIndex = picks 배열의 삽입 위치(이 트랙 '다음' = index+1).
function makeInserter(atIndex) {
  const zone = elDiv("track-inserter");
  zone.addEventListener("click", (e) => e.stopPropagation()); // 행 클릭(재생) 방지
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "inserter-btn";
  btn.title = "여기에 곡 추가";
  btn.setAttribute("aria-label", "여기에 곡 추가");
  btn.innerHTML =
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" ' +
    'stroke-linecap="round" aria-hidden="true"><path d="M8 3.5 V12.5 M3.5 8 H12.5"/></svg>';
  btn.addEventListener("click", () => openSongPickerAt(atIndex));
  zone.append(btn);
  return zone;
}

// 모바일은 호버가 없어 배지 툴팁을 탭으로 열고 닫는다(호버 가능한 기기는 mouseenter로도 열림).
// 툴팁 본체는 고정(fixed) 위치의 재사용 엘리먼트 1개 — 열 때마다 배지 위치를 재서
// 화면 가장자리에 잘리지 않게 좌우/상하로 클램프한다(창 크기·기기 방향에 맞춰 적응).
let openTooltipBadge = null;
let tooltipBox = null;
let tooltipText = null;
let tooltipArrow = null;
const TOOLTIP_MARGIN = 8;
const supportsHoverTooltip =
  typeof window.matchMedia === "function" &&
  window.matchMedia("(hover: hover) and (pointer: fine)").matches;

function ensureTooltipEl() {
  if (!tooltipBox) {
    tooltipBox = document.createElement("div");
    tooltipBox.className = "badge-tooltip";
    tooltipText = document.createElement("span");
    tooltipArrow = document.createElement("div");
    tooltipArrow.className = "arrow";
    tooltipBox.append(tooltipText, tooltipArrow);
    document.body.appendChild(tooltipBox);
  }
  return tooltipBox;
}

function positionTooltip(badgeEl) {
  const box = ensureTooltipEl();
  const rect = badgeEl.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const boxW = box.offsetWidth;
  const boxH = box.offsetHeight;

  let placeBelow = false;
  let top = rect.top - boxH - TOOLTIP_MARGIN;
  if (top < TOOLTIP_MARGIN) {
    placeBelow = true;
    top = rect.bottom + TOOLTIP_MARGIN;
  }
  top = Math.min(Math.max(top, TOOLTIP_MARGIN), Math.max(TOOLTIP_MARGIN, vh - boxH - TOOLTIP_MARGIN));

  const badgeCenterX = rect.left + rect.width / 2;
  let left = badgeCenterX - boxW / 2;
  left = Math.min(Math.max(left, TOOLTIP_MARGIN), vw - boxW - TOOLTIP_MARGIN);

  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
  box.classList.toggle("above", !placeBelow);
  box.classList.toggle("below", placeBelow);

  // 화살표는 박스가 가장자리에서 밀려도 배지 중심을 계속 가리키도록 별도 보정.
  const arrowLeft = Math.min(Math.max(badgeCenterX - left, 12), boxW - 12);
  tooltipArrow.style.left = `${arrowLeft}px`;
}

function showTooltip(badgeEl, text) {
  const box = ensureTooltipEl();
  tooltipText.textContent = text;
  box.classList.add("visible");
  positionTooltip(badgeEl); // visible 처리 후 측정해야 offsetWidth/Height가 정확함
}

function hideTooltipBox() {
  if (tooltipBox) tooltipBox.classList.remove("visible");
}

function closeOpenTooltip() {
  openTooltipBadge = null;
  hideTooltipBox();
}

window.addEventListener("resize", () => {
  if (openTooltipBadge) positionTooltip(openTooltipBadge);
});

// 툴팁이 열려 있을 때는 화면 어디를 클릭하든(다른 배지 포함) 그 클릭은 툴팁만 닫고
// 원래 하려던 동작(곡 재생 등)으로 이어지지 않는다 — capture 단계에서 가로채 전파를 끊는다.
document.addEventListener(
  "click",
  (e) => {
    if (openTooltipBadge) {
      e.preventDefault();
      e.stopPropagation();
      closeOpenTooltip();
    }
  },
  true,
);

function makeBadge(kind, label, tooltip) {
  const b = document.createElement("span");
  b.className = "badge" + (kind ? " " + kind : "");
  b.textContent = label;
  if (tooltip) {
    b.dataset.tooltip = tooltip;
    b.tabIndex = 0; // 키보드 포커스로도 툴팁 확인 가능
    b.addEventListener("click", (e) => {
      e.stopPropagation(); // 태그 클릭이 트랙 재생(행 클릭)으로 전파되지 않도록
      const willOpen = openTooltipBadge !== b;
      closeOpenTooltip();
      if (willOpen) {
        showTooltip(b, tooltip);
        openTooltipBadge = b;
      }
    });
    if (supportsHoverTooltip) {
      b.addEventListener("mouseenter", () => showTooltip(b, tooltip));
      b.addEventListener("mouseleave", () => {
        if (openTooltipBadge !== b) hideTooltipBox();
      });
    }
    b.addEventListener("focus", () => showTooltip(b, tooltip));
    b.addEventListener("blur", () => {
      if (openTooltipBadge !== b) hideTooltipBox();
    });
  }
  return b;
}

