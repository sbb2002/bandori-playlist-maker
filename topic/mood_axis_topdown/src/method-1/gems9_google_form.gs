/**
 * GEMS-9 설문 구글폼 자동 생성 스크립트 (script.google.com에서 실행)
 *
 * SONGS는 build_gems9_survey_data.py가 out/gems9_pilot_candidates.csv에서 자동 생성한다.
 * 구간(start/end)이 비어있던 곡은 폴백(인트로 0~30초)이 들어있고 isFallback=true로 표시됨 —
 * Tool 1(segment_picker_tool.html)로 구간을 확정한 CSV로 갱신한 뒤 파이썬 스크립트를
 * 다시 돌리면 이 배열도 함께 갱신되고, buildForm()을 다시 실행하면 새 폼이 그 값으로
 * 생성된다(기존 폼을 고치는 게 아니라 매번 새 폼을 만든다 — 여러 응답자에게 이미 링크가
 * 나간 뒤라면 재실행하지 말 것).
 *
 * 구간 강제(자동 정지)는 보장 안 됨 — setVideoUrl의 ?start= 파라미터가 Forms 임베드에서
 * 실제로 반영되는지 미검증. 대신 각 영상 문항 도움말에 권장 구간을 문구로 명시해 둔다.
 */

var SONGS = [
  {
    "idx": 31,
    "band": "afterglow",
    "song": "青い栞",
    "videoId": "bzJW33heiqw",
    "energyFull": 0.062021,
    "start": 157.57552203433227,
    "end": 187.3377019103546,
    "isFallback": false
  },
  {
    "idx": 61,
    "band": "afterglow",
    "song": "Redo (Cover)",
    "videoId": "Q5ld_AEJAWw",
    "energyFull": 0.493874,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 68,
    "band": "afterglow",
    "song": "Don't say “lazy” (Cover)",
    "videoId": "PThqwHLyPpU",
    "energyFull": 0.953292,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 91,
    "band": "ave_mujica",
    "song": "in your blue eyes",
    "videoId": "kVMuEQ3uXWc",
    "energyFull": 0.003828,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 94,
    "band": "ave_mujica",
    "song": "DIVINE",
    "videoId": "6bA-vjvi9oI",
    "energyFull": 0.1049,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 84,
    "band": "ave_mujica",
    "song": "Ave Mujica",
    "videoId": "QDsd0nyzwz0",
    "energyFull": 0.993109,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 131,
    "band": "hello_happy_world",
    "song": "ひまわりの約束",
    "videoId": "WC3paFpeKTo",
    "energyFull": 0.132466,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 135,
    "band": "hello_happy_world",
    "song": "コレカラ",
    "videoId": "9DpyAgb_DO8",
    "energyFull": 0.771057,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 157,
    "band": "hello_happy_world",
    "song": "強風オールバック (Cover)",
    "videoId": "EGxEKCHDAFE",
    "energyFull": 0.997703,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 178,
    "band": "ikka_dumb_rock",
    "song": "ホーミー・タイッ！！",
    "videoId": "BSP-xypGSak",
    "energyFull": 0.689127,
    "start": 143.6408519485016,
    "end": 173.41212595803833,
    "isFallback": false
  },
  {
    "idx": 179,
    "band": "millsage",
    "song": "起死開戦",
    "videoId": "bzPxdHmMW3s",
    "energyFull": 0.163859,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 189,
    "band": "morfonica",
    "song": "Sweet Cheers!",
    "videoId": "e8IQBZMVIGw",
    "energyFull": 0.045176,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 185,
    "band": "morfonica",
    "song": "fly with the night",
    "videoId": "DpnFf8UINbs",
    "energyFull": 0.232006,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 207,
    "band": "morfonica",
    "song": "わたしまちがいさがし",
    "videoId": "UgP_YbdsoB8",
    "energyFull": 0.959418,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 245,
    "band": "mugendai_mutype",
    "song": "テレパシー",
    "videoId": "mKiBvYqfBfk",
    "energyFull": 0.065084,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 239,
    "band": "mugendai_mutype",
    "song": "みゅーたんとミュータント",
    "videoId": "qnHJDWgLkvw",
    "energyFull": 0.826187,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 257,
    "band": "mugendai_mutype",
    "song": "やわやわNERD 超FreQuency",
    "videoId": "xzkEK0GF7fw",
    "energyFull": 0.99464,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 278,
    "band": "mygo",
    "song": "処救生",
    "videoId": "Z2OLVzWFaY0",
    "energyFull": 0.000766,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 298,
    "band": "mygo",
    "song": "swim (Cover)",
    "videoId": "YcBvpV_CzuU",
    "energyFull": 0.048239,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 300,
    "band": "mygo",
    "song": "春日影",
    "videoId": "wRwQUk0Dl30",
    "energyFull": 0.74196,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 339,
    "band": "pastel_palettes",
    "song": "everyday flower",
    "videoId": "zEHPkLXcX1I",
    "energyFull": 0.121746,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 341,
    "band": "pastel_palettes",
    "song": "フレっとパレットFight Song!!",
    "videoId": "ZvK22__1ECE",
    "energyFull": 0.709801,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 368,
    "band": "pastel_palettes",
    "song": "ハッピーシンセサイザ (Cover)",
    "videoId": "AD3WCMhAGVs",
    "energyFull": 0.999234,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 415,
    "band": "poppin_party",
    "song": "キミにもらったもの",
    "videoId": "gu85qKfXfj8",
    "energyFull": 0.066616,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 396,
    "band": "poppin_party",
    "song": "STAR BEAT!～ホシノコドウ～ ～Popipa Acoustic Ver.～",
    "videoId": "kj5orLd_XnA",
    "energyFull": 0.535222,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 414,
    "band": "poppin_party",
    "song": "夏のドーン！",
    "videoId": "xtgdECulbbw",
    "energyFull": 0.979326,
    "start": 148.44275121743775,
    "end": 177.80656303051757,
    "isFallback": false
  },
  {
    "idx": 536,
    "band": "raise_a_suilen",
    "song": "Drown Out the Noise and Push Through the Trash",
    "videoId": "EELGtL1U1vw",
    "energyFull": 0.039051,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 560,
    "band": "raise_a_suilen",
    "song": "Just Awake (Cover)",
    "videoId": "nyn9h6BraQ4",
    "energyFull": 0.590352,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 491,
    "band": "raise_a_suilen",
    "song": "A DECLARATION OF ×××",
    "videoId": "9iOltuunbvs",
    "energyFull": 0.996172,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 580,
    "band": "roselia",
    "song": "軌跡",
    "videoId": "P2BT98BC1N8",
    "energyFull": 0.042113,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 654,
    "band": "roselia",
    "song": "Paradisus‐Paradoxum (Cover)",
    "videoId": "A12CMqrBFSw",
    "energyFull": 0.43415,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 656,
    "band": "roselia",
    "song": "Preserved Roses (Cover)",
    "videoId": "rB5eL98q6f8",
    "energyFull": 0.977795,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 101,
    "band": "various_artists",
    "song": "Don't be afraid!",
    "videoId": "hPnvMOyGgzc",
    "energyFull": 0.454824,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 103,
    "band": "various_artists",
    "song": "Be shine, shining!",
    "videoId": "tv1Pf0FE6iw",
    "energyFull": 0.594181,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  },
  {
    "idx": 104,
    "band": "various_artists",
    "song": "Here, the world",
    "videoId": "LuwRRghPD1A",
    "energyFull": 0.673813,
    "start": 0.0,
    "end": 30.0,
    "isFallback": false
  }
];

var ITEMS = [
  { key: 'wonder', kr: '경이', desc: '우와 신기하다, 놀랍다는 느낌' },
  { key: 'transcendence', kr: '초월', desc: '성스럽거나 신비로운, 뭔가 큰 것과 이어진 느낌' },
  { key: 'tenderness', kr: '다정함', desc: '부드럽고 사랑스러운 느낌' },
  { key: 'nostalgia', kr: '향수', desc: '옛 생각나는, 그리운 느낌' },
  { key: 'peacefulness', kr: '평온함', desc: '마음이 편안하고 고요해지는 느낌' },
  { key: 'power', kr: '웅장함', desc: '힘이 넘치고 강한, 이겨내는 듯한 느낌' },
  { key: 'joyful_activation', kr: '활기', desc: '신나고 즐거운, 들뜨는 느낌' },
  { key: 'tension', kr: '긴장', desc: '불안하고 초조한 느낌' },
  { key: 'sadness', kr: '슬픔', desc: '슬프고 처연한 느낌' }
];

function formatTime(sec) {
  sec = Math.round(sec);
  var m = Math.floor(sec / 60);
  var s = sec % 60;
  return m + ':' + (s < 10 ? '0' : '') + s;
}

function buildForm() {
  var form = FormApp.create('GEMS-9 음악 감정 설문 (BanG Dream)');
  form.setDescription(
    '아래 순서대로 곡을 들으며 각 항목을 1~5점으로 채점해주세요.\n' +
    '1=전혀 못 느낌, 3=보통, 5=매우 강하게 느껴짐.\n' +
    '가사 내용이 아니라 곡 전체 느낌(멜로디·연주·분위기)으로 채점해주세요. 정답은 없습니다.\n' +
    '각 곡마다 안내되는 구간만 들어주세요(자동으로 그 구간만 재생되지 않을 수 있습니다).'
  );
  form.setProgressBar(true);
  form.setCollectEmail(false);

  form.addTextItem()
    .setTitle('응답자 이름 또는 별명')
    .setHelpText('분석 시 응답자 구분용입니다.')
    .setRequired(true);

  for (var i = 0; i < SONGS.length; i++) {
    var s = SONGS[i];
    var pageTitle = (i + 1) + '/' + SONGS.length + ' · ' + s.band + ' · ' + s.song;
    var timeLabel = formatTime(s.start) + '~' + formatTime(s.end);
    var fallbackNote = s.isFallback ? ' (구간 임시값 — 확정 아님)' : '';

    form.addPageBreakItem().setTitle(pageTitle);

    var video = form.addVideoItem();
    video.setVideoUrl('https://youtu.be/' + s.videoId + '?start=' + Math.floor(s.start));
    video.setTitle(pageTitle);
    video.setHelpText(
      '권장 구간: ' + timeLabel + fallbackNote +
      ' — 이 구간만 들어주세요(자동으로 정확히 멈추지 않을 수 있습니다).'
    );

    var grid = form.addGridItem();
    grid.setTitle(s.band + ' · ' + s.song + ' — 9개 항목 채점 [idx' + s.idx + ']');
    grid.setRows(ITEMS.map(function (it) { return it.kr + ' (' + it.desc + ')'; }));
    grid.setColumns(['1', '2', '3', '4', '5']);
    grid.setRequired(true);

    form.addParagraphTextItem()
      .setTitle('인상 메모(선택)')
      .setRequired(false);
  }

  Logger.log('폼 수정(편집) 링크: ' + form.getEditUrl());
  Logger.log('응답 링크(응답자에게 공유): ' + form.getPublishedUrl());
}
