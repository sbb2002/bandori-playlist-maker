// ── UI 헬퍼 ───────────────────────────────────────────────────────────────────
$("next-btn").addEventListener("click", () => playSong(current + 1, false));
$("prev-btn").addEventListener("click", () => playSong(current - 1, false));

// 전체 세트리스트 공유(B2) — 'YouTube 재생목록' 버튼 → 공유 팝업(안내·URL 복사·내 재생목록에 넣기).
// URL 복사는 watch_videos 익명 링크(OAuth 불필요). '내 재생목록에 넣기'는 사용자 자신의 Google
// 계정에 실제 YouTube 재생목록을 생성한다(OAuth + Data API, 클라이언트 사이드 토큰 플로우).
const shareModalEl = $("share-modal");
const shareUrlInputEl = $("share-url");
const ytSaveStatusEl = $("yt-save-status");
const ytOpenLinkEl = $("yt-open-link");
const ytSaveProgressEl = $("yt-save-progress");
const ytSaveProgressBarEl = $("yt-save-progress-bar");
let shareUrl = "";

$("yt-playlist-btn").addEventListener("click", () => {
  if (!picks.length) return;
  const ids = picks.map((p) => p.video_id).join(",");
  shareUrl = `https://www.youtube.com/watch_videos?video_ids=${ids}`;
  shareUrlInputEl.value = shareUrl;
  resetCopyBtn();
  hide(ytSaveStatusEl);
  hide(ytOpenLinkEl); // 지난 회차의 결과 링크가 남지 않도록 초기화
  show(shareModalEl);
  lockBodyScroll(true);
  track("playlist_shared", { count: picks.length });
});

$("share-open").addEventListener("click", saveToYouTubePlaylist);
$("share-copy").addEventListener("click", copyShareUrl);
shareModalEl.addEventListener("click", (e) => {
  if (e.target instanceof HTMLElement && e.target.dataset && "close" in e.target.dataset) closeShareModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !shareModalEl.classList.contains("hidden")) closeShareModal();
});

function closeShareModal() { hide(shareModalEl); lockBodyScroll(false); }
function resetCopyBtn() {
  const btn = $("share-copy");
  btn.textContent = "복사";
  btn.classList.remove("copied");
}

async function copyShareUrl() {
  const btn = $("share-copy");
  let ok = false;
  try {
    await navigator.clipboard.writeText(shareUrl);
    ok = true;
  } catch (_) {
    // 폴백: input 선택 후 execCommand(구형·클립보드 차단 환경).
    shareUrlInputEl.focus();
    shareUrlInputEl.select();
    try { ok = document.execCommand("copy"); } catch (_2) { ok = false; }
  }
  btn.textContent = ok ? "복사됨 ✓" : "직접 복사하세요";
  btn.classList.toggle("copied", ok);
  setTimeout(resetCopyBtn, 1500);
  if (ok) track("playlist_link_copied", { count: picks.length });
}

