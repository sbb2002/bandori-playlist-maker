// ── YouTube IFrame Player ─────────────────────────────────────────────────────
let player = null;
let ytReady = false;
let pendingStart = null;

window.onYouTubeIframeAPIReady = function () {
  ytReady = true;
  if (pendingStart) { const fn = pendingStart; pendingStart = null; fn(); }
};

function loadYouTubeApi() {
  if (window.YT && window.YT.Player) { ytReady = true; return; }
  if (document.getElementById("yt-api")) return;
  const s = document.createElement("script");
  s.id = "yt-api";
  s.src = "https://www.youtube.com/iframe_api";
  document.head.appendChild(s);
}

function startPlayback() {
  current = 0;
  loadedVideoId = picks[0].video_id;
  playbackStarted = false;
  highlight(0);
  updateNowPlaying(picks[0]);

  // song-sorter 검증 패턴: 빈 플레이어(생성자 videoId 없음) + autoplay 0.
  // 첫 곡은 cue만(자동재생 정책 위반 회피 — "An error occurred" 방지). 사용자가 ▶ 클릭 시 재생,
  // 이후 곡은 loadVideoById로 자동 전환(상호작용 이후이므로 자동재생 허용).
  const boot = () => {
    if (player && typeof player.cueVideoById === "function") {
      player.cueVideoById(picks[0].video_id);
      return;
    }
    player = new YT.Player("player", {
      height: "100%",
      width: "100%",
      playerVars: { autoplay: 0, modestbranding: 1, rel: 0, controls: 1, playsinline: 1 },
      events: {
        onReady: () => player.cueVideoById(picks[0].video_id),
        onStateChange: onPlayerStateChange,
        onError: onPlayerError,
      },
    });
  };

  if (ytReady) boot();
  else { pendingStart = boot; loadYouTubeApi(); }
}

function onPlayerStateChange(e) {
  if (e.data === YT.PlayerState.PLAYING) {
    errorSkips = 0; // 정상 재생 시 스킵 가드 리셋
    playbackStarted = true; // 이후 편집 시 load(자동재생) 허용
    setPlaybarPlaying(true);
    startPlaybarProgressTimer();
  } else if (e.data === YT.PlayerState.PAUSED) {
    setPlaybarPlaying(false);
    stopPlaybarProgressTimer();
  } else if (e.data === YT.PlayerState.ENDED) {
    stopPlaybarProgressTimer();
    setPlaybarPlaying(false);
    playedSeconds += safeDuration();
    maybeFireHalf();
    if (repeatMode === "one") {
      player.seekTo(0, true);
      player.playVideo();
    } else if (current + 1 < picks.length) {
      playSong(current + 1, true);
    } else if (repeatMode === "all") {
      playSong(0, true); // 마지막 곡까지 다 돌았으면 처음으로
    }
  }
}

// 재생불가(삭제·임베드차단·연령제한·지역락) → 다음 곡 자동 스킵.
function onPlayerError(e) {
  const p = picks[current];
  console.warn("YouTube 재생 오류", e && e.data, "video", p && p.video_id);
  errorSkips += 1;
  if (errorSkips > picks.length) {
    showError("재생 가능한 영상을 찾지 못했어요. 다른 요청을 시도해 보세요.");
    return;
  }
  if (current + 1 < picks.length) {
    playSong(current + 1, true);
  } else {
    showError("이 영상은 재생할 수 없어요. 아래 'YouTube에서 열기'로 시청해 주세요.");
  }
}

function playSong(index, auto) {
  if (index < 0 || index >= picks.length) return;
  current = index;
  const p = picks[index];
  loadedVideoId = p.video_id;
  highlight(index, auto);
  updateNowPlaying(p);
  // 사용자 클릭/자동 전환 — 상호작용 이후이므로 loadVideoById(자동재생) 사용.
  if (player && typeof player.loadVideoById === "function") player.loadVideoById(p.video_id);
  if (auto) track("song_advance", { position: p.position, idx: p.idx });
}

function safeDuration() {
  try {
    const d = player && player.getDuration ? player.getDuration() : 0;
    return d && d > 0 ? d : AVG_SONG_SECONDS;
  } catch (_) {
    return AVG_SONG_SECONDS;
  }
}

function maybeFireHalf() {
  if (halfFired || estimatedTotal <= 0) return;
  if (playedSeconds >= estimatedTotal * 0.5) {
    halfFired = true;
    track("playlist_half_played", { played_seconds: Math.round(playedSeconds) });
  }
}

