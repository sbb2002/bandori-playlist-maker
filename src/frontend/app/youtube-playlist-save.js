// ── '내 재생목록에 넣기' — Google OAuth(GIS 토큰 클라이언트) + YouTube Data API v3 ──────────────
// 백엔드 미관여(client secret 없음, 브라우저에서 직접 access token 발급·API 호출). 실패 시
// picks/현재 재생 상태는 절대 건드리지 않고 조기 반환한다(요구사항: 앱 상태 그대로 유지).
const YT_SCOPE = "https://www.googleapis.com/auth/youtube.force-ssl";
let ytAccessToken = null;
let ytTokenClient = null;
let ytTokenPending = null; // 진행 중인 토큰 요청의 { resolve, reject } — 콜백에서 한 번만 결착
let ytSaving = false;      // 저장 진행 중 재진입 방지

function settleToken(ok, value) {
  if (!ytTokenPending) return;
  const pending = ytTokenPending;
  ytTokenPending = null;
  if (ok) pending.resolve(value);
  else pending.reject(value);
}

function getYouTubeTokenClient() {
  if (!ytTokenClient) {
    ytTokenClient = google.accounts.oauth2.initTokenClient({
      client_id: window.GOOGLE_CLIENT_ID,
      scope: YT_SCOPE,
      callback: (resp) => {
        if (resp && resp.error) settleToken(false, new Error(resp.error));
        else { ytAccessToken = resp.access_token; settleToken(true, ytAccessToken); }
      },
      // 팝업을 닫거나(popup_closed) 팝업이 아예 안 뜨면(popup_failed_to_open) GIS는 callback이
      // 아니라 이쪽으로 알린다. 이걸 안 달면 약속이 영영 결착되지 않아 버튼이 잠긴 채 멈춘다
      // — 인증 심사 중인 앱에서 비테스트 계정은 '차단' 화면을 닫는 것 외엔 할 게 없으므로
      // 사실상 모든 일반 사용자가 그 상태에 빠졌다.
      error_callback: (err) => settleToken(false, new Error((err && err.type) || "popup_error")),
    });
  }
  return ytTokenClient;
}

function ensureYouTubeToken({ forcePrompt = false } = {}) {
  if (ytAccessToken && !forcePrompt) return Promise.resolve(ytAccessToken);
  return new Promise((resolve, reject) => {
    settleToken(false, new Error("superseded")); // 이전 요청이 남아 있으면 먼저 정리
    ytTokenPending = { resolve, reject };
    getYouTubeTokenClient().requestAccessToken({ prompt: forcePrompt ? "consent" : "" });
  });
}

async function createYouTubePlaylist(token, title) {
  const res = await fetch("https://www.googleapis.com/youtube/v3/playlists?part=snippet,status", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      snippet: { title, description: t("ytsave.playlistDescription") },
      status: { privacyStatus: "unlisted" },
    }),
  });
  if (!res.ok) {
    const err = new Error(`playlists.insert failed: ${res.status}`);
    err.status = res.status;
    throw err;
  }
  const data = await res.json();
  return data.id;
}

async function addVideoToPlaylist(token, playlistId, videoId, position) {
  const res = await fetch("https://www.googleapis.com/youtube/v3/playlistItems?part=snippet", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      snippet: { playlistId, position, resourceId: { kind: "youtube#video", videoId } },
    }),
  });
  if (!res.ok) throw new Error(`playlistItems.insert failed: ${res.status}`);
}

// YouTube Data API v3에 배치 삽입 엔드포인트가 없어(HTTP batch는 2020년경 지원 종료) 순차 호출한다.
// 병렬 호출은 할당량을 더 빨리 태우고 순서 보장이 깨질 수 있어 피한다.
async function addAllVideosToPlaylist(token, playlistId, picksToAdd, onProgress) {
  const succeeded = [];
  const failed = [];
  for (let i = 0; i < picksToAdd.length; i++) {
    const p = picksToAdd[i];
    try {
      await addVideoToPlaylist(token, playlistId, p.video_id, i);
      succeeded.push(p.video_id);
    } catch (e) {
      failed.push({ video_id: p.video_id, error: String(e) });
    }
    onProgress(i + 1, picksToAdd.length);
  }
  return { succeeded, failed };
}

function setYtSaveStatus(text) {
  ytSaveStatusEl.textContent = text;
  show(ytSaveStatusEl);
}

function setYtProgress(n, total) {
  ytSaveProgressBarEl.style.width = `${Math.round((n / total) * 100)}%`;
  show(ytSaveProgressEl);
}

function hideYtProgress() {
  hide(ytSaveProgressEl);
  ytSaveProgressBarEl.style.width = "0%";
}

// 결과(또는 폴백) 열기 링크를 띄운다. window.open도 함께 시도하지만, OAuth 팝업이 닫힌 뒤라
// 사용자 제스처가 끊겨 팝업 차단에 막히는 경우가 많고 noopener면 성공 여부도 알 수 없다
// → 눌러서 확실히 열 수 있는 링크를 항상 함께 제공한다.
function offerYtOpenLink(url, label) {
  ytOpenLinkEl.href = url;
  ytOpenLinkEl.textContent = label;
  show(ytOpenLinkEl);
  window.open(url, "_blank", "noopener");
}

// 내 계정 저장이 불가능한 예외 상황(인증 심사 중 계정 차단·할당량 소진 등)의 폴백 —
// 이 기능 도입 전의 동작인 익명 watch_videos 임시 재생목록(YouTube에 'Untitled List'로 표시)으로
// 되돌린다. picks/재생 상태는 건드리지 않는다.
function openAnonymousPlaylistFallback(reason) {
  setYtSaveStatus(t("ytsave.fallbackNote", { reason }));
  offerYtOpenLink(shareUrl, t("ytsave.openTempPlaylist"));
  track("playlist_save_fallback_anonymous", { count: picks.length });
}

async function saveToYouTubePlaylist() {
  if (!picks.length || ytSaving) return;
  const btn = $("share-open");
  ytSaving = true;
  btn.disabled = true;
  hideYtProgress();
  hide(ytOpenLinkEl);
  setYtSaveStatus(t("ytsave.checkingLogin"));

  try {
    let token;
    try {
      token = await ensureYouTubeToken();
    } catch (e) {
      // 로그인 취소·팝업 닫힘, 그리고 인증(verification) 심사 중이라 계정이 차단된 경우가 모두 여기로 온다.
      track("playlist_save_auth_failed", { count: picks.length, reason: String((e && e.message) || e) });
      openAnonymousPlaylistFallback(t("ytsave.googleSaveFail"));
      return; // picks/재생 상태 불변
    }

    setYtSaveStatus(t("ytsave.creating"));
    const title = (lastParams && lastParams.interpretation_summary)
      || t("ytsave.defaultTitle", { date: new Date().toISOString().slice(0, 10) });
    let playlistId;
    try {
      playlistId = await createYouTubePlaylist(token, title);
    } catch (e) {
      if (e.status === 401) {
        try {
          token = await ensureYouTubeToken({ forcePrompt: true });
          playlistId = await createYouTubePlaylist(token, title);
        } catch (_2) {
          playlistId = null;
        }
      }
      if (!playlistId) {
        track("playlist_save_create_failed", { count: picks.length });
        openAnonymousPlaylistFallback(t("ytsave.createFail"));
        return;
      }
    }

    const { succeeded, failed } = await addAllVideosToPlaylist(token, playlistId, picks, (n, total) => {
      setYtSaveStatus(t("ytsave.addingProgress", { n, total }));
      setYtProgress(n, total);
    });
    hideYtProgress();

    const playlistUrl = `https://www.youtube.com/playlist?list=${playlistId}`;
    if (failed.length === 0) {
      setYtSaveStatus(t("ytsave.savedOk"));
      offerYtOpenLink(playlistUrl, t("ytsave.openMyPlaylist"));
    } else if (succeeded.length > 0) {
      setYtSaveStatus(t("ytsave.partial", { picks: picks.length, succeeded: succeeded.length }));
      offerYtOpenLink(playlistUrl, t("ytsave.openMyPlaylist"));
    } else {
      openAnonymousPlaylistFallback(t("ytsave.addFail"));
      return;
    }
    track("playlist_saved_to_account", { count: picks.length, succeeded: succeeded.length, failed: failed.length });
  } finally {
    // 어떤 경로로 빠져나가든 버튼은 반드시 되살린다(예외가 나도 잠기지 않게).
    ytSaving = false;
    btn.disabled = false;
    hideYtProgress();
  }
}

