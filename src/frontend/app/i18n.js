/* 다국어(i18n) — KO(기본)/JA/EN/zh-Hans/zh-Hant. app/*.js 로드 순서 안내: 이 파일이 항상
 * 첫 번째로 로드된다(utils.js보다도 먼저) — 다른 모든 모듈이 t()/tArr()/i18n.setLang을
 * 참조하므로 그 무엇에도 의존하지 않는 leaf 파일이어야 한다(utils.js 헤더 코멘트의 규칙과 동일).
 *
 * 브랜드명("Bandream Playlist Maker" 등)·고유명사(Camelot, YouTube, Google, 밴드명)는
 * 번역하지 않고 모든 언어에서 그대로 둔다. 언어 선택 팝업의 언어명("한국어"/"日本語"/...)도
 * 항상 해당 언어 자체 표기로 고정(index.html에 하드코딩, i18n 대상 아님).
 */
"use strict";

const I18N_STORAGE_KEY = "lang";
const SUPPORTED_LANGS = ["ko", "ja", "en", "zh-Hans", "zh-Hant"];
const DEFAULT_LANG = "ko";
// <html lang="..">용 BCP47 태그(zh-Hans/zh-Hant는 내부 코드와 표준 태그가 다름).
const HTML_LANG_TAG = { ko: "ko", ja: "ja", en: "en", "zh-Hans": "zh-CN", "zh-Hant": "zh-TW" };

// key → { ko, ja, en, "zh-Hans", "zh-Hant" } 한 행씩. 값이 배열이면 그대로 배열로 취급(tArr()).
const I18N_TABLE = {
  // ── 공통 ──────────────────────────────────────────────────────────────────
  "common.close": { ko: "닫기", ja: "閉じる", en: "Close", "zh-Hans": "关闭", "zh-Hant": "關閉" },
  "common.delete": { ko: "삭제", ja: "削除", en: "Delete", "zh-Hans": "删除", "zh-Hant": "刪除" },
  "common.minuteUnit": { ko: "분", ja: "分", en: "min", "zh-Hans": "分钟", "zh-Hant": "分鐘" },

  // ── 상단 메뉴/테마/언어 ───────────────────────────────────────────────────────
  "menu.open": { ko: "메뉴 열기", ja: "メニューを開く", en: "Open menu", "zh-Hans": "打开菜单", "zh-Hant": "開啟選單" },
  "menu.close": { ko: "메뉴 닫기", ja: "メニューを閉じる", en: "Close menu", "zh-Hans": "关闭菜单", "zh-Hant": "關閉選單" },
  "menu.title": { ko: "저장된 플레이리스트", ja: "保存したプレイリスト", en: "Saved playlists", "zh-Hans": "已保存的播放列表", "zh-Hant": "已儲存的播放清單" },
  "menu.empty": {
    ko: "아직 저장된 플레이리스트가 없어요.<br>플레이리스트를 만들면 자동으로 저장돼요.",
    ja: "まだ保存したプレイリストがありません。<br>プレイリストを作ると自動的に保存されます。",
    en: "No saved playlists yet.<br>Playlists are saved automatically when you create one.",
    "zh-Hans": "还没有已保存的播放列表。<br>创建播放列表后会自动保存。",
    "zh-Hant": "還沒有已儲存的播放清單。<br>建立播放清單後會自動儲存。",
  },
  "menu.versionLabel": { ko: "현재 버전", ja: "現在のバージョン", en: "Current version", "zh-Hans": "当前版本", "zh-Hant": "目前版本" },
  "theme.toggle": { ko: "다크 모드 전환", ja: "ダークモード切替", en: "Toggle dark mode", "zh-Hans": "切换深色模式", "zh-Hant": "切換深色模式" },
  "lang.select": { ko: "언어 선택", ja: "言語を選択", en: "Select language", "zh-Hans": "选择语言", "zh-Hant": "選擇語言" },

  // ── Hero ─────────────────────────────────────────────────────────────────
  "hero.logoAlt": { ko: "Bandream Playlist Maker 로고", ja: "Bandream Playlist Maker ロゴ", en: "Bandream Playlist Maker logo", "zh-Hans": "Bandream Playlist Maker 徽标", "zh-Hant": "Bandream Playlist Maker 標誌" },
  "hero.subtitle": {
    ko: "유메와빠와~ 한 문장으로 뱅드림 플레이리스트를 말아드립니다.",
    ja: "ゆめゔぁー！ひとことでバンドリのプレイリストをお作りします。",
    en: "Yumewapawa~ Just one sentence, and we'll whip up a BanG Dream! playlist for you.",
    "zh-Hans": "梦与帕华~ 只需一句话，为你打造 BanG Dream! 播放列表。",
    "zh-Hant": "夢與帕華~ 只需一句話，為你打造 BanG Dream! 播放清單。",
  },

  // ── 모드 전환 ─────────────────────────────────────────────────────────────
  "mode.switchAria": { ko: "생성 모드 전환 — AI 모드 또는 커스텀 모드", ja: "生成モード切替 — AIモードまたはカスタムモード", en: "Switch generation mode — AI mode or Custom mode", "zh-Hans": "切换生成模式 — AI 模式或自定义模式", "zh-Hant": "切換產生模式 — AI 模式或自訂模式" },
  "mode.ai": { ko: "AI 모드", ja: "AIモード", en: "AI Mode", "zh-Hans": "AI 模式", "zh-Hant": "AI 模式" },
  "mode.custom": { ko: "커스텀 모드", ja: "カスタムモード", en: "Custom Mode", "zh-Hans": "自定义模式", "zh-Hant": "自訂模式" },

  // ── 프롬프트 입력 ────────────────────────────────────────────────────────────
  "form.promptLabel": { ko: "어떤 플레이리스트를 원하세요?", ja: "どんなプレイリストが欲しいですか？", en: "What kind of playlist do you want?", "zh-Hans": "你想要什么样的播放列表？", "zh-Hant": "你想要什麼樣的播放清單？" },
  "form.promptPlaceholder": {
    ko: "예) 퇴근하고 주말 시작! 기분이 절로 좋아지는 1시간 플레이리스트",
    ja: "例）仕事終わりで週末スタート！気分が上がる1時間プレイリスト",
    en: "e.g. Off work, weekend starts now! An upbeat 1-hour playlist to lift my mood",
    "zh-Hans": "例：下班啦周末开始！让心情变好的1小时播放列表",
    "zh-Hant": "例：下班啦週末開始！讓心情變好的1小時播放清單",
  },
  "form.promptMaxLen": { ko: "⚠️ {{n}}자까지만 적을 수 있어요.", ja: "⚠️ 最大{{n}}文字まで入力できます。", en: "⚠️ You can enter up to {{n}} characters.", "zh-Hans": "⚠️ 最多只能输入 {{n}} 个字符。", "zh-Hant": "⚠️ 最多只能輸入 {{n}} 個字元。" },
  "omakase.aria": { ko: "오마카세로 프롬프트 자동 생성", ja: "おまかせでプロンプト自動生成", en: "Auto-generate a prompt (Omakase)", "zh-Hans": "随心一键生成提示词", "zh-Hant": "隨心一鍵產生提示詞" },
  "omakase.title": { ko: "오마카세", ja: "おまかせ", en: "Omakase", "zh-Hans": "随心一选", "zh-Hant": "隨心一選" },
  "omakase.generating": { ko: "오마카세 프롬프트 생성 중…", ja: "おまかせプロンプト生成中…", en: "Generating an Omakase prompt…", "zh-Hans": "正在生成随机提示词…", "zh-Hant": "正在產生隨機提示詞…" },

  // ── 세부 설정 ─────────────────────────────────────────────────────────────
  "options.summary": { ko: "세부 설정 (선택)", ja: "詳細設定（任意）", en: "Advanced settings (optional)", "zh-Hans": "详细设置（可选）", "zh-Hant": "詳細設定（可選）" },
  "options.guide": {
    ko: "여기서 플레이리스트를 직접 다듬을 수 있어요. 바꾼 설정은 같은 요청에서 유지되고, 프롬프트를 새 내용으로 바꾸면 다시 자동으로 맞춰드려요.",
    ja: "ここでプレイリストを直接調整できます。変更した設定は同じリクエスト内で維持され、プロンプトを新しい内容に変えると再び自動で合わせます。",
    en: "Fine-tune your playlist here. Your changes stick for this request — if you type a new prompt, we'll re-match everything automatically.",
    "zh-Hans": "你可以在这里直接调整播放列表。修改的设置会在本次请求中保留；如果更换提示词，会自动重新匹配。",
    "zh-Hant": "你可以在這裡直接調整播放清單。修改的設定會在本次請求中保留；如果更換提示詞，會自動重新配對。",
  },
  "options.minutesLabel": { ko: "플레이리스트 재생시간", ja: "プレイリストの再生時間", en: "Playlist length", "zh-Hans": "播放列表时长", "zh-Hant": "播放清單時長" },
  "options.minutesNote1": { ko: "플레이리스트의 총 재생시간이에요.", ja: "プレイリスト全体の再生時間です。", en: "This is the total playback time.", "zh-Hans": "这是播放列表的总时长。", "zh-Hant": "這是播放清單的總時長。" },
  "options.minutesNote2": { ko: "최소 30분, 최대 180분 가능해요.", ja: "最短30分〜最長180分で設定できます。", en: "Set between 30 and 180 minutes.", "zh-Hans": "可设置 30 到 180 分钟。", "zh-Hant": "可設定 30 到 180 分鐘。" },
  "options.minutesPlaceholder": { ko: "60(기본)", ja: "60（デフォルト）", en: "60 (default)", "zh-Hans": "60（默认）", "zh-Hant": "60（預設）" },
  "options.minutesMax": { ko: "⚠️ 최대 3시간(180분)까지 설정할 수 있어요.", ja: "⚠️ 最大3時間（180分）まで設定できます。", en: "⚠️ You can set up to 3 hours (180 min).", "zh-Hans": "⚠️ 最多可设置 3 小时（180 分钟）。", "zh-Hant": "⚠️ 最多可設定 3 小時（180 分鐘）。" },
  "options.typeLabel": { ko: "곡 종류", ja: "曲の種類", en: "Song type", "zh-Hans": "歌曲类型", "zh-Hant": "歌曲類型" },
  "options.typeNote1": { ko: "오리지날 또는 커버 곡만 들어볼 수도 있어요.", ja: "オリジナルまたはカバー曲だけを聴くこともできます。", en: "You can listen to only originals or only covers.", "zh-Hans": "你也可以只听原创曲或翻唱曲。", "zh-Hant": "你也可以只聽原創曲或翻唱曲。" },
  "options.typeNote2": { ko: "물론 둘다도 들어볼 수 있죠!", ja: "もちろん両方聴くこともできます！", en: "Or listen to both, of course!", "zh-Hans": "当然也可以两种都听！", "zh-Hant": "當然也可以兩種都聽！" },
  "options.bandLabel": { ko: "듣고싶은 밴드", ja: "聴きたいバンド", en: "Bands you want to hear", "zh-Hans": "想听的乐队", "zh-Hant": "想聽的樂團" },
  "options.bandClearAll": { ko: "전체 해제", ja: "全解除", en: "Clear all", "zh-Hans": "全部取消", "zh-Hant": "全部取消" },
  "options.bandNote1": { ko: "듣고 싶은 밴드만 선택해볼 수 있죠!", ja: "聴きたいバンドだけを選ぶこともできます！", en: "Pick only the bands you want to hear!", "zh-Hans": "只选择你想听的乐队吧！", "zh-Hant": "只選擇你想聽的樂團吧！" },
  "options.bandNote2": { ko: "모두 해제하면 모든 밴드가 선택되요.", ja: "すべて解除するとすべてのバンドが対象になります。", en: "Clear all selections to include every band.", "zh-Hans": "全部取消勾选即代表包含所有乐队。", "zh-Hant": "全部取消勾選即代表包含所有樂團。" },
  "options.bandLoading": { ko: "밴드 목록 불러오는 중…", ja: "バンド一覧を読み込み中…", en: "Loading band list…", "zh-Hans": "正在加载乐队列表…", "zh-Hant": "正在載入樂團清單…" },
  "options.bandLoadError": { ko: "밴드 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).", ja: "バンド一覧を読み込めませんでした（バックエンドが起動しているか確認してください）。", en: "Couldn't load the band list (check that the backend is running).", "zh-Hans": "无法加载乐队列表（请确认后端是否已启动）。", "zh-Hant": "無法載入樂團清單（請確認後端是否已啟動）。" },
  "options.bandNone": { ko: "밴드 없음", ja: "バンドがありません", en: "No bands", "zh-Hans": "暂无乐队", "zh-Hant": "暫無樂團" },

  "options.stageLabel": { ko: "플레이리스트 구간 설정", ja: "プレイリスト区間設定", en: "Playlist stage settings", "zh-Hans": "播放列表分段设置", "zh-Hant": "播放清單分段設定" },
  "options.stageMinus": { ko: "구간 줄이기", ja: "区間を減らす", en: "Fewer stages", "zh-Hans": "减少分段", "zh-Hant": "減少分段" },
  "options.stagePlus": { ko: "구간 늘리기", ja: "区間を増やす", en: "More stages", "zh-Hans": "增加分段", "zh-Hant": "增加分段" },
  "options.stageCount": { ko: "{{n}}구간", ja: "{{n}}区間", en: "{{n}} stages", "zh-Hans": "{{n}} 段", "zh-Hant": "{{n}} 段" },
  "options.timebarSub": { ko: "구간 시간길이 정하기", ja: "区間ごとの長さを決める", en: "Set stage durations", "zh-Hans": "设置各分段时长", "zh-Hant": "設定各分段時長" },
  "options.timebarEqualize": { ko: "모두 균일하게", ja: "すべて均等に", en: "Make all equal", "zh-Hans": "全部平均分配", "zh-Hant": "全部平均分配" },
  "options.timebarNote1": { ko: "구간에 따라 시간을 자유롭게 정해보세요.", ja: "区間ごとに時間を自由に決めてみましょう。", en: "Freely set the time for each stage.", "zh-Hans": "可以自由设置每个分段的时长。", "zh-Hant": "可以自由設定每個分段的時長。" },
  "options.timebarNote2": { ko: "각 구간은 최소 3분 이상이에요.", ja: "各区間は最短3分以上です。", en: "Each stage is at least 3 minutes.", "zh-Hans": "每个分段至少 3 分钟。", "zh-Hant": "每個分段至少 3 分鐘。" },
  "options.timebarNote3": { ko: "우측에 '모두 균일하게' 버튼을 누르면 모든 구간의 시간을 균일하게 맞춰요.", ja: "右側の「すべて均等に」ボタンを押すと、すべての区間の時間を均等にそろえます。", en: "Press 'Make all equal' on the right to even out every stage's length.", "zh-Hans": "点击右侧的“全部平均分配”按钮，可让所有分段时长保持一致。", "zh-Hant": "點擊右側的「全部平均分配」按鈕，可讓所有分段時長保持一致。" },

  "options.impressionSub": { ko: "구간 가사 감성 정하기 및 밴드 설정", ja: "区間の歌詞の雰囲気とバンド設定", en: "Set lyric mood and bands per stage", "zh-Hans": "设置各分段的歌词氛围与乐队", "zh-Hant": "設定各分段的歌詞氛圍與樂團" },
  "options.impressionNote1": { ko: "구간에 따라 원하는 감성을 입력해보세요!", ja: "区間ごとに欲しい雰囲気を入力してみましょう！", en: "Type the mood you want for each stage!", "zh-Hans": "为每个分段输入你想要的氛围吧！", "zh-Hant": "為每個分段輸入你想要的氛圍吧！" },
  "options.impressionNote2": { ko: "감성과 어울리는 가사를 가진 노래를 찾아줘요. 비워둬도 상관없어요!", ja: "その雰囲気に合う歌詞の曲を探します。空欄のままでも大丈夫です！", en: "We'll find songs with lyrics matching that mood. It's fine to leave it blank!", "zh-Hans": "我们会寻找歌词符合该氛围的歌曲。留空也没关系！", "zh-Hant": "我們會尋找歌詞符合該氛圍的歌曲。留空也沒關係！" },
  "options.impressionNote3": { ko: "일부 구간에서 특정밴드만 듣고 싶으면 '밴드 고정' 버튼을 눌러보세요!", ja: "特定の区間で特定のバンドだけ聴きたいときは「バンド固定」ボタンを押してみましょう！", en: "Want only certain bands in a stage? Try the 'Fix bands' button!", "zh-Hans": "想在某个分段只听特定乐队？试试“固定乐队”按钮吧！", "zh-Hant": "想在某個分段只聽特定樂團？試試「固定樂團」按鈕吧！" },
  "options.impressionNote4": { ko: "듣고싶은 밴드 중에서 1개 이상 지정할 수 있어요.", ja: "聴きたいバンドの中から1つ以上指定できます。", en: "Pick one or more bands from your chosen list.", "zh-Hans": "可以从想听的乐队中指定 1 个或以上。", "zh-Hant": "可以從想聽的樂團中指定 1 個或以上。" },
  "options.impressionItemLabel": { ko: "구간", ja: "区間", en: "Stage", "zh-Hans": "分段", "zh-Hant": "分段" },
  "options.bandFix": { ko: "밴드 고정", ja: "バンド固定", en: "Fix bands", "zh-Hans": "固定乐队", "zh-Hant": "固定樂團" },
  "options.impressionExamples": {
    ko: ["설레고 두근거리는 마음", "지치고 무거운 마음을 다독이는 위로", "터질 듯한 흥분과 해방감", "쓸쓸하고 애틋한 그리움", "작은 희망을 붙잡는 담담한 의지"],
    ja: ["ときめいてドキドキする気持ち", "疲れて重い心を慰める癒やし", "はち切れそうな興奮と解放感", "寂しく切ない恋しさ", "小さな希望をつかむ静かな意志"],
    en: ["A fluttery, excited heart", "Comfort for a tired, heavy heart", "Bursting excitement and release", "A lonely, wistful longing", "Quiet resolve holding onto a small hope"],
    "zh-Hans": ["心动又雀跃的心情", "抚慰疲惫沉重内心的温暖", "几乎要爆发的兴奋与释放感", "孤寂又惆怅的思念", "紧握微小希望的平静意志"],
    "zh-Hant": ["心動又雀躍的心情", "撫慰疲憊沉重內心的溫暖", "幾乎要爆發的興奮與釋放感", "孤寂又惆悵的思念", "緊握微小希望的平靜意志"],
  },

  "options.energyLabel": { ko: "에너지 X 감정 궤적", ja: "エネルギー×感情の軌跡", en: "Energy × Mood trajectory", "zh-Hans": "能量 × 情绪轨迹", "zh-Hant": "能量 × 情緒軌跡" },
  "options.energyNote1": { ko: "듣고 싶은 노래의 에너지와 감정을 조절해보세요!", ja: "聴きたい曲のエネルギーと感情を調整してみましょう！", en: "Adjust the energy and mood of the songs you want!", "zh-Hans": "调整你想听的歌曲的能量与情绪吧！", "zh-Hant": "調整你想聽的歌曲的能量與情緒吧！" },
  "options.energyNote2": { ko: "노란색으로 갈수록 밝고 신나는 노래가, 녹색으로 갈수록 밝고 잔잔한 노래가 나와요.", ja: "黄色に近いほど明るく楽しい曲、緑に近いほど明るく穏やかな曲になります。", en: "More yellow means brighter, more upbeat songs; more green means brighter, more mellow songs.", "zh-Hans": "越偏黄色，歌曲越明快兴奋；越偏绿色，歌曲越明亮舒缓。", "zh-Hant": "越偏黃色，歌曲越明快興奮；越偏綠色，歌曲越明亮舒緩。" },
  "options.energyNote3": { ko: "빨간색으로 갈수록 무겁고 격렬한 노래가, 파란색으로 갈수록 차분하고 가라앉은 노래가 나와요.", ja: "赤に近いほど重く激しい曲、青に近いほど落ち着いた沈んだ曲になります。", en: "More red means heavier, more intense songs; more blue means calmer, more subdued songs.", "zh-Hans": "越偏红色，歌曲越沉重激烈；越偏蓝色，歌曲越沉静低回。", "zh-Hant": "越偏紅色，歌曲越沉重激烈；越偏藍色，歌曲越沉靜低迴。" },
  "options.energyNote4": { ko: "구간 포인트를 드래그해서 원하는 곳에 놓으세요. 시간에 따라 그 감성으로 진행되요!", ja: "区間ポイントをドラッグして好きな場所に置いてください。時間の流れとともにその雰囲気で進みます！", en: "Drag each stage point wherever you like — the playlist will flow through that mood over time!", "zh-Hans": "把分段圆点拖到你想要的位置吧，播放列表会随时间朝该情绪推进！", "zh-Hant": "把分段圓點拖到你想要的位置吧，播放清單會隨時間朝該情緒推進！" },
  "options.quadrantHeavy": { ko: "무겁고<br />격렬한", ja: "重く<br />激しい", en: "Heavy &<br />Intense", "zh-Hans": "沉重<br />激烈", "zh-Hant": "沉重<br />激烈" },
  "options.quadrantBright": { ko: "밝고<br />신나는", ja: "明るく<br />楽しい", en: "Bright &<br />Upbeat", "zh-Hans": "明快<br />兴奋", "zh-Hant": "明快<br />興奮" },
  "options.quadrantCalm": { ko: "차분하고<br />가라앉은", ja: "落ち着いた<br />沈んだ", en: "Calm &<br />Subdued", "zh-Hans": "沉静<br />低回", "zh-Hant": "沉靜<br />低迴" },
  "options.quadrantSoft": { ko: "밝고<br />잔잔한", ja: "明るく<br />穏やかな", en: "Bright &<br />Mellow", "zh-Hans": "明亮<br />舒缓", "zh-Hant": "明亮<br />舒緩" },
  "options.advancedLabel": { ko: "고급 설정", ja: "高度な設定", en: "Advanced settings", "zh-Hans": "高级设置", "zh-Hant": "進階設定" },

  "param.lufs.label": { ko: "라우드니스", ja: "ラウドネス", en: "Loudness", "zh-Hans": "响度", "zh-Hant": "響度" },
  "param.lufs.desc": { ko: "높을수록 크고 힘있는 곡이, 낮을수록 조용한 곡이 선택되요.", ja: "高いほど力強い曲、低いほど静かな曲が選ばれます。", en: "Higher picks bigger, more powerful songs; lower picks quieter songs.", "zh-Hans": "数值越高越会选出响亮有力的歌曲，越低越安静。", "zh-Hant": "數值越高越會選出響亮有力的歌曲，越低越安靜。" },
  "param.lra.label": { ko: "다이내믹 범위", ja: "ダイナミックレンジ", en: "Dynamic range", "zh-Hans": "动态范围", "zh-Hant": "動態範圍" },
  "param.lra.desc": { ko: "높을수록 점점 벅차오르는 느낌이! 낮을수록 조곤조곤한 느낌의 곡이 선택되요.", ja: "高いほど徐々に盛り上がる感じ！低いほど落ち着いた語り口調の曲が選ばれます。", en: "Higher feels like a swelling build-up; lower picks steadier, even-keeled songs.", "zh-Hans": "数值越高越有渐渐澎湃的感觉！越低越会选出平缓细语般的歌曲。", "zh-Hant": "數值越高越有漸漸澎湃的感覺！越低越會選出平緩細語般的歌曲。" },
  "param.dance.label": { ko: "리듬감", ja: "リズム感", en: "Danceability", "zh-Hans": "律动感", "zh-Hant": "律動感" },
  "param.dance.desc": { ko: "높을수록 일정한 리듬을 가진 곡이, 낮을수록 변칙적인 리듬의 곡이 선택되요. 둠칫둠칫~", ja: "高いほど一定のリズムの曲、低いほど変則的なリズムの曲が選ばれます。ズンズン〜", en: "Higher picks songs with a steady beat; lower picks songs with an unpredictable rhythm. Boom-tss~", "zh-Hans": "数值越高越会选出节奏规律的歌曲，越低越不规则。咚吃咚吃~", "zh-Hant": "數值越高越會選出節奏規律的歌曲，越低越不規則。咚吃咚吃~" },
  "param.instr.label": { ko: "악기 비중", ja: "楽器の比重", en: "Instrumental ratio", "zh-Hans": "乐器占比", "zh-Hant": "樂器佔比" },
  "param.instr.desc": { ko: "높을수록 악기 비중이 높은 곡이, 낮을수록 보컬 비중이 높은 곡이 선택되요.", ja: "高いほど楽器の比重が高い曲、低いほどボーカルの比重が高い曲が選ばれます。", en: "Higher picks more instrument-forward songs; lower picks more vocal-forward songs.", "zh-Hans": "数值越高越会选出乐器占比高的歌曲，越低人声占比越高。", "zh-Hant": "數值越高越會選出樂器佔比高的歌曲，越低人聲佔比越高。" },
  "param.speech.label": { ko: "음절밀도", ja: "音節密度", en: "Syllable density", "zh-Hans": "音节密度", "zh-Hant": "音節密度" },
  "param.speech.desc": { ko: "높을수록 속사포 랩같은 곡이, 낮을수록 멜로디가 있는 곡이 선택됩니다.", ja: "高いほど早口ラップのような曲、低いほどメロディアスな曲が選ばれます。", en: "Higher picks rapid-fire, rap-like songs; lower picks more melodic songs.", "zh-Hans": "数值越高越会选出连珠炮般的说唱风歌曲，越低越有旋律感。", "zh-Hant": "數值越高越會選出連珠炮般的饒舌風歌曲，越低越有旋律感。" },

  "paramShort.valence": { ko: "밝기", ja: "明るさ", en: "Mood", "zh-Hans": "明快度", "zh-Hant": "明快度" },
  "paramShort.lufs": { ko: "라우드", ja: "音量", en: "Loud", "zh-Hans": "响度", "zh-Hant": "響度" },
  "paramShort.lra": { ko: "다이내믹", ja: "抑揚", en: "Dynamic", "zh-Hans": "动态", "zh-Hant": "動態" },
  "paramShort.dance": { ko: "리듬감", ja: "リズム", en: "Dance", "zh-Hans": "律动", "zh-Hant": "律動" },
  "paramShort.instr": { ko: "악기", ja: "楽器", en: "Instr.", "zh-Hans": "乐器", "zh-Hant": "樂器" },
  "paramShort.speech": { ko: "음절", ja: "音節", en: "Syllable", "zh-Hans": "音节", "zh-Hant": "音節" },

  "submit.button": { ko: "플레이리스트 만들기", ja: "プレイリストを作る", en: "Make my playlist", "zh-Hans": "生成播放列表", "zh-Hant": "產生播放清單" },

  // ── 로딩 ─────────────────────────────────────────────────────────────────
  "loading.messages": {
    ko: ["플레이리스트를 만드는 중입니다~ 🎶", "요청을 무드로 해석하고 있어요… 🔮", "곡을 하모닉하게 잇는 중… 🎼", "에너지 흐름을 다듬는 중… 📈", "당신을 위한 곡을 고르고 있어요… ✨"],
    ja: ["プレイリストを作っています〜 🎶", "リクエストをムードに解釈中… 🔮", "曲をハーモニックにつないでいます… 🎼", "エネルギーの流れを整えています… 📈", "あなたのために曲を選んでいます… ✨"],
    en: ["Building your playlist~ 🎶", "Reading the mood of your request… 🔮", "Harmonically mixing the songs… 🎼", "Smoothing out the energy flow… 📈", "Picking songs just for you… ✨"],
    "zh-Hans": ["正在生成播放列表~ 🎶", "正在解析你的情绪需求… 🔮", "正在和谐地串联歌曲… 🎼", "正在调整能量走向… 📈", "正在为你挑选歌曲… ✨"],
    "zh-Hant": ["正在產生播放清單~ 🎶", "正在解析你的情緒需求… 🔮", "正在和諧地串聯歌曲… 🎼", "正在調整能量走向… 📈", "正在為你挑選歌曲… ✨"],
  },
  "loading.text": { ko: "플레이리스트를 만드는 중입니다~ 🎶", ja: "プレイリストを作っています〜 🎶", en: "Building your playlist~ 🎶", "zh-Hans": "正在生成播放列表~ 🎶", "zh-Hant": "正在產生播放清單~ 🎶" },
  "loading.sub": { ko: "백엔드가 잠들어 있었다면 첫 응답이 조금 느릴 수 있어요.", ja: "バックエンドがスリープしていた場合、最初の応答が少し遅れることがあります。", en: "If the backend was asleep, the first response may take a little longer.", "zh-Hans": "如果后端处于休眠状态，首次响应可能会稍慢一些。", "zh-Hant": "如果後端處於休眠狀態，首次回應可能會稍慢一些。" },
  "loading.coldstart": { ko: "서버가 잠깐 자고 있었나 봐요… 깨우는 중이에요! 🥱☕ (유메와 파와—!)", ja: "サーバーが少し眠っていたみたい… 起こしています！ 🥱☕（ゆめゔぁー！）", en: "Looks like the server dozed off… waking it up now! 🥱☕ (Yumewapawa—!)", "zh-Hans": "服务器好像打了个盹… 正在唤醒中！🥱☕（梦与帕华—！）", "zh-Hant": "伺服器好像打了個盹… 正在喚醒中！🥱☕（夢與帕華—！）" },

  // ── 결과 요약/에러 ────────────────────────────────────────────────────────
  "error.noMatch": { ko: "조건에 맞는 곡을 찾지 못했어요. 요청을 조금 바꿔 보세요.", ja: "条件に合う曲が見つかりませんでした。リクエストを少し変えてみてください。", en: "We couldn't find songs matching your request. Try tweaking it a bit.", "zh-Hans": "没有找到符合条件的歌曲，试着修改一下你的请求吧。", "zh-Hant": "沒有找到符合條件的歌曲，試著修改一下你的請求吧。" },
  "error.needStages": { ko: "구간 설정을 해 주세요.", ja: "区間を設定してください。", en: "Please set up at least one stage.", "zh-Hans": "请先设置分段。", "zh-Hant": "請先設定分段。" },
  "error.requestFailed": { ko: "요청 실패 (HTTP {{status}})", ja: "リクエスト失敗（HTTP {{status}}）", en: "Request failed (HTTP {{status}})", "zh-Hans": "请求失败（HTTP {{status}}）", "zh-Hant": "請求失敗（HTTP {{status}}）" },
  "error.backendDown": { ko: "백엔드에 연결하지 못했어요. 서버가 켜져 있는지, API 주소가 맞는지 확인해 주세요.", ja: "バックエンドに接続できませんでした。サーバーが起動しているか、API アドレスが正しいか確認してください。", en: "Couldn't connect to the backend. Please check that the server is running and the API address is correct.", "zh-Hans": "无法连接到后端。请确认服务器是否已启动、API 地址是否正确。", "zh-Hant": "無法連線到後端。請確認伺服器是否已啟動、API 位址是否正確。" },
  "error.queueRegisterFail": { ko: "대기열 등록에 실패했어요. 잠시 후 다시 시도해 주세요.", ja: "待機列への登録に失敗しました。しばらくしてからもう一度お試しください。", en: "Couldn't join the queue. Please try again in a moment.", "zh-Hans": "加入队列失败，请稍后重试。", "zh-Hant": "加入佇列失敗，請稍後再試一次。" },
  "error.queueTimeout": { ko: "대기 시간이 너무 길어져 요청을 취소했어요. 잠시 후 다시 시도해 주세요.", ja: "待機時間が長くなりすぎたためリクエストをキャンセルしました。しばらくしてからもう一度お試しください。", en: "The wait got too long, so we cancelled the request. Please try again in a moment.", "zh-Hans": "等待时间过长，请求已取消，请稍后重试。", "zh-Hant": "等待時間過長，請求已取消，請稍後再試一次。" },
  "error.noPlayable": { ko: "재생 가능한 영상을 찾지 못했어요. 다른 요청을 시도해 보세요.", ja: "再生可能な動画が見つかりませんでした。別のリクエストを試してみてください。", en: "Couldn't find a playable video. Try a different request.", "zh-Hans": "没有找到可播放的视频，试试其他请求吧。", "zh-Hant": "沒有找到可播放的影片，試試其他請求吧。" },
  "error.cantPlay": { ko: "이 영상은 재생할 수 없어요. 아래 'YouTube에서 열기'로 시청해 주세요.", ja: "この動画は再生できません。下の「YouTubeで開く」からご覧ください。", en: "This video can't be played here. Please watch it via 'Open in YouTube' below.", "zh-Hans": "此视频无法播放，请通过下方的“在 YouTube 中打开”观看。", "zh-Hant": "此影片無法播放，請透過下方的「在 YouTube 中開啟」觀看。" },
  "edit.allRemoved": { ko: "모든 곡을 제거했어요. 새 요청을 만들거나 되돌리기(Ctrl+Z) 하세요.", ja: "すべての曲を削除しました。新しいリクエストを作るか、元に戻す（Ctrl+Z）を使ってください。", en: "All songs were removed. Make a new request or undo (Ctrl+Z).", "zh-Hans": "已移除所有歌曲。请重新生成或撤销（Ctrl+Z）。", "zh-Hant": "已移除所有歌曲。請重新產生或復原（Ctrl+Z）。" },

  "queue.ahead": { ko: "내 앞에 {{n}}명 대기 중. ", ja: "自分の前に{{n}}人待機中。", en: "{{n}} ahead of you in line. ", "zh-Hans": "你前面还有 {{n}} 人在等待。", "zh-Hant": "你前面還有 {{n}} 人在等待。" },
  "queue.soonWithAhead": { ko: "{{ahead}}곧 시작할게요! 🙏", ja: "{{ahead}}まもなく開始します！ 🙏", en: "{{ahead}}Starting soon! 🙏", "zh-Hans": "{{ahead}}马上就开始！🙏", "zh-Hant": "{{ahead}}馬上就開始！🙏" },
  // 대기 인원이 없는데도(queue_position=0) waitSeconds<=0이면 뜨는 문구 — 흔히 "혼잡"이 아니라
  // 레이트리밋 게이트는 이미 통과하고 순수 LLM 응답만 기다리는 정상 케이스라(routes.py
  // acquired_event 참고), "요청이 몰려서" 같은 혼잡 암시 표현은 부정확하다. 정체 여부와
  // 무관하게 항상 맞는 중립적 "거의 다 됨" 문구로 둔다.
  "queue.wrappingUp": { ko: "거의 다 됐어요! 조금만 기다려 주세요 🙏", ja: "もうすぐ完成です！少々お待ちください 🙏", en: "Almost done! Just a moment 🙏", "zh-Hans": "马上就好啦！请稍等 🙏", "zh-Hant": "馬上就好啦！請稍候 🙏" },
  "queue.eta": { ko: "{{ahead}}약 {{sec}}초 정도 걸릴 것 같아요… ⏳", ja: "{{ahead}}約{{sec}}秒ほどかかりそうです… ⏳", en: "{{ahead}}About {{sec}}s to go… ⏳", "zh-Hans": "{{ahead}}大约还需 {{sec}} 秒… ⏳", "zh-Hant": "{{ahead}}大約還需 {{sec}} 秒… ⏳" },

  "summary.defaultInterp": { ko: "요청에 맞춰 세트리스트를 구성했어요.", ja: "リクエストに合わせてセットリストを構成しました。", en: "We built a setlist to match your request.", "zh-Hans": "已根据你的请求生成歌单。", "zh-Hant": "已根據你的請求產生歌單。" },
  "summary.songCount": { ko: "{{n}}곡", ja: "{{n}}曲", en: "{{n}} songs", "zh-Hans": "{{n}} 首", "zh-Hant": "{{n}} 首" },
  "summary.approxMinutes": { ko: "약 {{n}}분", ja: "約{{n}}分", en: "~{{n}} min", "zh-Hans": "约 {{n}} 分钟", "zh-Hant": "約 {{n}} 分鐘" },

  // ── 트랙 배지(하모닉) ─────────────────────────────────────────────────────
  "harmonic.seed.label": { ko: "시작곡", ja: "起点曲", en: "Opener", "zh-Hans": "起始曲", "zh-Hant": "起始曲" },
  "harmonic.seed.tooltip": { ko: "세트리스트의 첫 곡이라 직전 곡과 비교할 조성이 없어요.", ja: "セットリストの最初の曲のため、比較する前の曲の調がありません。", en: "This is the first song, so there's no previous key to compare against.", "zh-Hans": "这是歌单的第一首歌，没有可比较的前一首曲调。", "zh-Hant": "這是歌單的第一首歌，沒有可比較的前一首調性。" },
  "harmonic.same.label": { ko: "동일조성", ja: "同一調", en: "Same key", "zh-Hans": "同调", "zh-Hant": "同調" },
  "harmonic.same.tooltip": { ko: "직전 곡과 조성이 완전히 같아요. 조옮김 없이 그대로 이어져 가장 매끄러운 전환이에요.", ja: "直前の曲と調が完全に同じです。転調なしでそのままつながる最も滑らかな展開です。", en: "The exact same key as the previous song — the smoothest possible transition, no key change at all.", "zh-Hans": "与前一首曲调完全相同，无需转调即可无缝衔接，是最流畅的过渡。", "zh-Hant": "與前一首調性完全相同，無需轉調即可無縫銜接，是最流暢的過渡。" },
  "harmonic.adjacent.label": { ko: "하모닉인접", ja: "ハーモニック隣接", en: "Harmonic neighbor", "zh-Hans": "和声邻近", "zh-Hant": "和聲鄰近" },
  "harmonic.adjacent.tooltip": { ko: "직전 곡과 Camelot Wheel 기준으로 인접한 조성이에요(관계조 또는 5도 이웃). 공통음이 많아 자연스럽게 넘어가요.", ja: "直前の曲とCamelot Wheel上で隣接する調です（関係調または5度圏の隣）。共通音が多く自然につながります。", en: "Adjacent to the previous song's key on the Camelot Wheel (relative key or a fifth apart). Shares enough common notes for a natural transition.", "zh-Hans": "与前一首在 Camelot Wheel 上相邻（关系调或五度邻近调），共同音较多，过渡自然。", "zh-Hant": "與前一首在 Camelot Wheel 上相鄰（關係調或五度鄰近調），共同音較多，過渡自然。" },
  "harmonic.non_harmonic.label": { ko: "조성전환", ja: "転調", en: "Key change", "zh-Hans": "转调", "zh-Hant": "轉調" },
  "harmonic.non_harmonic.tooltip": { ko: "직전 곡과 조성이 같지도, 인접하지도 않아요. 곡 경계에서 조성이 크게 바뀌는 전환이에요.", ja: "直前の曲と調が同じでも隣接してもいません。曲の境目で調が大きく変わる展開です。", en: "Neither the same key nor adjacent to the previous song — a bigger key shift at this boundary.", "zh-Hans": "与前一首既非同调，也不相邻，是曲目衔接处的较大转调。", "zh-Hant": "與前一首既非同調，也不相鄰，是曲目銜接處的較大轉調。" },
  "harmonic.added.label": { ko: "추가한 곡", ja: "追加した曲", en: "Added song", "zh-Hans": "手动添加", "zh-Hant": "手動新增" },
  "harmonic.added.tooltip": { ko: "직접 추가한 곡이라 하모닉 배치 로직이 적용되지 않았어요.", ja: "手動で追加した曲のため、ハーモニック配置ロジックは適用されていません。", en: "You added this song manually, so the harmonic-mixing logic wasn't applied.", "zh-Hans": "这是你手动添加的歌曲，未套用和声排列逻辑。", "zh-Hant": "這是你手動新增的歌曲，未套用和聲排列邏輯。" },
  "track.keyTooltip": { ko: "조성(Camelot {{code}})", ja: "調（Camelot {{code}}）", en: "Key (Camelot {{code}})", "zh-Hans": "调性（Camelot {{code}}）", "zh-Hant": "調性（Camelot {{code}}）" },

  // ── 플레이어 컨트롤 ───────────────────────────────────────────────────────
  "player.prev": { ko: "이전 곡", ja: "前の曲", en: "Previous track", "zh-Hans": "上一首", "zh-Hant": "上一首" },
  "player.next": { ko: "다음 곡", ja: "次の曲", en: "Next track", "zh-Hans": "下一首", "zh-Hant": "下一首" },
  "player.shareTitle": { ko: "전체를 YouTube 재생목록으로 열기", ja: "全曲をYouTube再生リストで開く", en: "Open the whole set as a YouTube playlist", "zh-Hans": "以 YouTube 播放列表打开全部歌曲", "zh-Hant": "以 YouTube 播放清單開啟全部歌曲" },
  "player.shareText": { ko: "🔗 내 플리 공유하기", ja: "🔗 プレイリストを共有", en: "🔗 Share my playlist", "zh-Hans": "🔗 分享我的播放列表", "zh-Hant": "🔗 分享我的播放清單" },
  "player.play": { ko: "재생", ja: "再生", en: "Play", "zh-Hans": "播放", "zh-Hant": "播放" },
  "player.pause": { ko: "일시정지", ja: "一時停止", en: "Pause", "zh-Hans": "暂停", "zh-Hant": "暫停" },
  "player.openYoutube": { ko: "YouTube에서 열기 ↗", ja: "YouTubeで開く ↗", en: "Open in YouTube ↗", "zh-Hans": "在 YouTube 中打开 ↗", "zh-Hant": "在 YouTube 中開啟 ↗" },

  "playbar.regionAria": { ko: "재생 바", ja: "再生バー", en: "Playback bar", "zh-Hans": "播放栏", "zh-Hant": "播放列" },
  "playbar.seekAria": { ko: "재생 위치", ja: "再生位置", en: "Playback position", "zh-Hans": "播放进度", "zh-Hant": "播放進度" },
  "playbar.gotoPlayerAria": { ko: "플레이어로 이동", ja: "プレーヤーへ移動", en: "Go to player", "zh-Hans": "前往播放器", "zh-Hant": "前往播放器" },
  "playbar.repeatOffTitle": { ko: "반복 (꺼짐)", ja: "リピート（オフ）", en: "Repeat (off)", "zh-Hans": "循环（关闭）", "zh-Hant": "循環（關閉）" },
  "playbar.repeatOffAria": { ko: "한 곡 반복 켜기", ja: "1曲リピートをオンにする", en: "Turn on repeat one", "zh-Hans": "开启单曲循环", "zh-Hant": "開啟單曲循環" },
  "playbar.repeatOneTitle": { ko: "한 곡 반복 (켜짐)", ja: "1曲リピート（オン）", en: "Repeat one (on)", "zh-Hans": "单曲循环（开启）", "zh-Hant": "單曲循環（開啟）" },
  "playbar.repeatOneAria": { ko: "전체 반복으로 전환", ja: "全曲リピートに切り替え", en: "Switch to repeat all", "zh-Hans": "切换为全部循环", "zh-Hant": "切換為全部循環" },
  "playbar.repeatAllTitle": { ko: "전체 반복 (켜짐)", ja: "全曲リピート（オン）", en: "Repeat all (on)", "zh-Hans": "全部循环（开启）", "zh-Hant": "全部循環（開啟）" },
  "playbar.repeatAllAria": { ko: "반복 끄기", ja: "リピートをオフにする", en: "Turn off repeat", "zh-Hans": "关闭循环", "zh-Hant": "關閉循環" },

  // ── Camelot Wheel ────────────────────────────────────────────────────────
  "wheel.summary": { ko: "조성 궤적 보기 (Camelot Wheel)", ja: "調の軌跡を見る（Camelot Wheel）", en: "View key trajectory (Camelot Wheel)", "zh-Hans": "查看调性轨迹（Camelot Wheel）", "zh-Hant": "檢視調性軌跡（Camelot Wheel）" },
  "wheel.caption": { ko: "선은 재생 순서를 따라가요.", ja: "線は再生順に沿っています。", en: "The lines follow the playback order.", "zh-Hans": "连线沿着播放顺序绘制。", "zh-Hant": "連線沿著播放順序繪製。" },
  "wheel.keyNameBtn": { ko: "음이름", ja: "音名", en: "Key name", "zh-Hans": "音名", "zh-Hant": "音名" },
  "wheel.guide1": { ko: "점 하나가 곡 한 곡, 점 위 숫자는 재생 순서예요.", ja: "点1つが曲1曲、点の上の数字は再生順です。", en: "Each dot is one song; the number on it is the play order.", "zh-Hans": "每个点代表一首歌，点上的数字是播放顺序。", "zh-Hant": "每個點代表一首歌，點上的數字是播放順序。" },
  "wheel.guide2": {
    ko: '<span style="color:var(--ok)">초록 실선</span>은 자연스럽게 이어지는 구간, <span style="color:var(--warn)">주황 점선</span>은 분위기가 훅 바뀌는 구간이에요.',
    ja: '<span style="color:var(--ok)">緑の実線</span>は自然につながる区間、<span style="color:var(--warn)">オレンジの点線</span>は雰囲気ががらりと変わる区間です。',
    en: 'A <span style="color:var(--ok)">solid green line</span> means a smooth transition; a <span style="color:var(--warn)">dashed orange line</span> means a sharp mood shift.',
    "zh-Hans": '<span style="color:var(--ok)">绿色实线</span>表示自然衔接的区间，<span style="color:var(--warn)">橙色虚线</span>表示氛围突变的区间。',
    "zh-Hant": '<span style="color:var(--ok)">綠色實線</span>表示自然銜接的區間，<span style="color:var(--warn)">橙色虛線</span>表示氛圍驟變的區間。',
  },
  "wheel.guide3": { ko: "점을 클릭하면 그 곡으로 바로 이동해요.", ja: "点をクリックするとその曲にすぐ移動します。", en: "Click a dot to jump straight to that song.", "zh-Hans": "点击圆点即可直接跳转到该曲目。", "zh-Hant": "點擊圓點即可直接跳轉到該曲目。" },
  "wheel.guide4": { ko: "점들이 원 안에서 좁게 모여 있을수록 통일된 분위기, 넓게 퍼져 있을수록 다채로운 분위기의 플레이리스트예요.", ja: "点が円の中で狭く集まっているほど統一感のある雰囲気、広く散らばっているほど多彩な雰囲気のプレイリストです。", en: "Dots clustered tightly mean a unified mood; dots spread wide mean a more varied, colorful playlist.", "zh-Hans": "点越集中，氛围越统一；点越分散，播放列表越丰富多彩。", "zh-Hant": "點越集中，氛圍越統一；點越分散，播放清單越豐富多彩。" },
  "wheel.guide5": { ko: "실선이 많을수록 쭉 이어 듣기 좋은 흐름, 점선이 많을수록 곡마다 분위기가 확확 바뀌는 구성이에요.", ja: "実線が多いほど通しで聴きやすい流れ、点線が多いほど曲ごとに雰囲気ががらりと変わる構成です。", en: "More solid lines mean an easy continuous flow; more dashed lines mean each song shifts the mood sharply.", "zh-Hans": "实线越多，越适合一气呵成地听；虚线越多，每首歌的氛围转折越明显。", "zh-Hant": "實線越多，越適合一氣呵成地聽；虛線越多，每首歌的氛圍轉折越明顯。" },

  // ── 트랙 편집/메뉴 ────────────────────────────────────────────────────────
  "track.addNext": { ko: "다음 곡 추가", ja: "次に曲を追加", en: "Add song after this", "zh-Hans": "在此曲后添加", "zh-Hant": "在此曲後新增" },
  "track.removeCurrent": { ko: "현재 곡 제거", ja: "この曲を削除", en: "Remove this song", "zh-Hans": "移除此曲", "zh-Hant": "移除此曲" },
  "track.moveTitle": { ko: "잡고 위아래로 드래그해 순서 이동", ja: "つかんで上下にドラッグして並び替え", en: "Drag up or down to reorder", "zh-Hans": "按住上下拖动以调整顺序", "zh-Hant": "按住上下拖曳以調整順序" },
  "track.moveAria": { ko: "순서 이동 (드래그)", ja: "並び替え（ドラッグ）", en: "Reorder (drag)", "zh-Hans": "拖动排序", "zh-Hant": "拖曳排序" },
  "track.removeTitle": { ko: "이 곡 제거", ja: "この曲を削除", en: "Remove this song", "zh-Hans": "移除此曲", "zh-Hant": "移除此曲" },
  "track.removeAria": { ko: "곡 제거", ja: "曲を削除", en: "Remove song", "zh-Hans": "移除歌曲", "zh-Hant": "移除歌曲" },
  "track.addHere": { ko: "여기에 곡 추가", ja: "ここに曲を追加", en: "Add a song here", "zh-Hans": "在此处添加歌曲", "zh-Hant": "在此處新增歌曲" },

  // ── 곡 추가 미니 브라우저 ─────────────────────────────────────────────────
  "picker.ariaLabel": { ko: "곡 추가", ja: "曲を追加", en: "Add song", "zh-Hans": "添加歌曲", "zh-Hant": "新增歌曲" },
  "picker.title": { ko: "곡 추가", ja: "曲を追加", en: "Add song", "zh-Hans": "添加歌曲", "zh-Hant": "新增歌曲" },
  "picker.insertFirst": { ko: "맨 앞에 삽입", ja: "先頭に挿入", en: "Insert at the start", "zh-Hans": "插入到最前面", "zh-Hant": "插入到最前面" },
  "picker.insertAfter": { ko: "{{n}}번 다음에 삽입", ja: "{{n}}番の次に挿入", en: "Insert after #{{n}}", "zh-Hans": "插入到第 {{n}} 首之后", "zh-Hant": "插入到第 {{n}} 首之後" },
  "picker.searchPlaceholder": { ko: "곡·밴드 검색", ja: "曲・バンド検索", en: "Search songs or bands", "zh-Hans": "搜索歌曲或乐队", "zh-Hant": "搜尋歌曲或樂團" },
  "picker.loading": { ko: "곡 목록 불러오는 중…", ja: "曲一覧を読み込み中…", en: "Loading songs…", "zh-Hans": "正在加载歌曲列表…", "zh-Hant": "正在載入歌曲清單…" },
  "picker.loadError": { ko: "곡 목록을 불러오지 못했어요 (백엔드가 켜져 있는지 확인).", ja: "曲一覧を読み込めませんでした（バックエンドが起動しているか確認してください）。", en: "Couldn't load the song list (check that the backend is running).", "zh-Hans": "无法加载歌曲列表（请确认后端是否已启动）。", "zh-Hant": "無法載入歌曲清單（請確認後端是否已啟動）。" },
  "picker.allBands": { ko: "전체", ja: "すべて", en: "All", "zh-Hans": "全部", "zh-Hant": "全部" },
  "picker.noResults": { ko: "일치하는 곡이 없어요.", ja: "一致する曲がありません。", en: "No matching songs.", "zh-Hans": "没有找到匹配的歌曲。", "zh-Hant": "沒有找到符合的歌曲。" },
  "picker.songMeta": { ko: "{{band}} · {{key}} · 에너지 {{energy}}", ja: "{{band}} · {{key}} · エネルギー {{energy}}", en: "{{band}} · {{key}} · Energy {{energy}}", "zh-Hans": "{{band}} · {{key}} · 能量 {{energy}}", "zh-Hant": "{{band}} · {{key}} · 能量 {{energy}}" },
  "picker.add": { ko: "추가", ja: "追加", en: "Add", "zh-Hans": "添加", "zh-Hant": "新增" },
  "picker.moreResults": { ko: "+{{n}}곡 더 있음 — 검색으로 좁혀 주세요", ja: "他に{{n}}曲あります — 検索で絞り込んでください", en: "+{{n}} more songs — narrow it down with search", "zh-Hans": "还有 {{n}} 首 — 请使用搜索缩小范围", "zh-Hant": "還有 {{n}} 首 — 請使用搜尋縮小範圍" },
  "picker.directAdd": { ko: "직접 추가한 곡", ja: "直接追加した曲", en: "Manually added song", "zh-Hans": "手动添加的歌曲", "zh-Hant": "手動新增的歌曲" },

  // ── 공유 팝업 ─────────────────────────────────────────────────────────────
  "share.ariaLabel": { ko: "플레이리스트 공유", ja: "プレイリストを共有", en: "Share playlist", "zh-Hans": "分享播放列表", "zh-Hant": "分享播放清單" },
  "share.title": { ko: "플레이리스트가 생성되었어요 🎉", ja: "プレイリストが作成されました 🎉", en: "Your playlist is ready 🎉", "zh-Hans": "播放列表已生成 🎉", "zh-Hant": "播放清單已產生 🎉" },
  "share.desc1": { ko: "내 플리를 다른 방붕이에게 공유하려면...", ja: "自分のプレイリストを友達に共有するには…", en: "To share your playlist with friends...", "zh-Hans": "想把播放列表分享给朋友…", "zh-Hant": "想把播放清單分享給朋友…" },
  "share.urlAriaLabel": { ko: "공유 링크", ja: "共有リンク", en: "Share link", "zh-Hans": "分享链接", "zh-Hant": "分享連結" },
  "share.copy": { ko: "복사", ja: "コピー", en: "Copy", "zh-Hans": "复制", "zh-Hant": "複製" },
  "share.copied": { ko: "복사됨 ✓", ja: "コピーしました ✓", en: "Copied ✓", "zh-Hans": "已复制 ✓", "zh-Hant": "已複製 ✓" },
  "share.copyManual": { ko: "직접 복사하세요", ja: "手動でコピーしてください", en: "Please copy it manually", "zh-Hans": "请手动复制", "zh-Hant": "請手動複製" },
  "share.desc2": { ko: "이 플리를 내 YouTube 계정에 추가하려면...", ja: "このプレイリストを自分のYouTubeアカウントに追加するには…", en: "To add this playlist to your own YouTube account...", "zh-Hans": "想把这份歌单加入自己的 YouTube 账号…", "zh-Hant": "想把這份歌單加入自己的 YouTube 帳號…" },
  "share.addToMyPlaylist": { ko: "내 재생목록에 넣기", ja: "自分の再生リストに追加", en: "Save to my playlist", "zh-Hans": "保存到我的播放列表", "zh-Hant": "儲存到我的播放清單" },
  "share.footnote": { ko: "※ Google 로그인 후 내 계정에 실제 YouTube 재생목록으로 저장돼요(일부공개).", ja: "※ Googleログイン後、実際のYouTube再生リストとしてアカウントに保存されます（限定公開）。", en: "※ After signing in with Google, this is saved to your account as a real (unlisted) YouTube playlist.", "zh-Hans": "※ 使用 Google 登录后，会以真实的 YouTube 播放列表（不公开）保存到你的账号。", "zh-Hant": "※ 使用 Google 登入後，會以真實的 YouTube 播放清單（不公開）儲存到你的帳號。" },

  // ── YouTube 재생목록 저장 ────────────────────────────────────────────────
  "ytsave.playlistDescription": { ko: "Bandori Playlist Maker에서 생성됨", ja: "Bandori Playlist Makerで作成", en: "Created with Bandori Playlist Maker", "zh-Hans": "由 Bandori Playlist Maker 生成", "zh-Hant": "由 Bandori Playlist Maker 產生" },
  "ytsave.checkingLogin": { ko: "Google 로그인 확인 중...", ja: "Googleログインを確認中...", en: "Checking Google sign-in...", "zh-Hans": "正在确认 Google 登录状态…", "zh-Hant": "正在確認 Google 登入狀態…" },
  "ytsave.creating": { ko: "재생목록 만드는 중...", ja: "再生リストを作成中...", en: "Creating playlist...", "zh-Hans": "正在创建播放列表…", "zh-Hant": "正在建立播放清單…" },
  "ytsave.defaultTitle": { ko: "뱅드림 세트리스트 ({{date}})", ja: "バンドリ セットリスト（{{date}}）", en: "BanG Dream! Setlist ({{date}})", "zh-Hans": "BanG Dream! 歌单（{{date}}）", "zh-Hant": "BanG Dream! 歌單（{{date}}）" },
  "ytsave.addingProgress": { ko: "곡 추가 중... ({{n}}/{{total}})", ja: "曲を追加中...（{{n}}/{{total}}）", en: "Adding songs... ({{n}}/{{total}})", "zh-Hans": "正在添加歌曲…（{{n}}/{{total}}）", "zh-Hant": "正在新增歌曲…（{{n}}/{{total}}）" },
  "ytsave.savedOk": { ko: "내 계정에 저장했어요 ✓", ja: "アカウントに保存しました ✓", en: "Saved to your account ✓", "zh-Hans": "已保存到你的账号 ✓", "zh-Hant": "已儲存到你的帳號 ✓" },
  "ytsave.openMyPlaylist": { ko: "내 재생목록 열기 ↗", ja: "自分の再生リストを開く ↗", en: "Open my playlist ↗", "zh-Hans": "打开我的播放列表 ↗", "zh-Hant": "開啟我的播放清單 ↗" },
  "ytsave.partial": { ko: "{{picks}}곡 중 {{succeeded}}곡만 추가됐어요. 나머지는 YouTube에서 직접 추가해주세요.", ja: "{{picks}}曲中{{succeeded}}曲のみ追加されました。残りはYouTubeで直接追加してください。", en: "Only {{succeeded}} of {{picks}} songs were added. Please add the rest directly on YouTube.", "zh-Hans": "{{picks}} 首中仅成功添加 {{succeeded}} 首，其余请直接在 YouTube 上添加。", "zh-Hant": "{{picks}} 首中僅成功新增 {{succeeded}} 首，其餘請直接在 YouTube 上新增。" },
  "ytsave.googleSaveFail": { ko: "Google 계정에 저장하지 못했어요.", ja: "Googleアカウントに保存できませんでした。", en: "Couldn't save to your Google account.", "zh-Hans": "无法保存到 Google 账号。", "zh-Hant": "無法儲存到 Google 帳號。" },
  "ytsave.createFail": { ko: "재생목록을 만들지 못했어요.", ja: "再生リストを作成できませんでした。", en: "Couldn't create the playlist.", "zh-Hans": "无法创建播放列表。", "zh-Hant": "無法建立播放清單。" },
  "ytsave.addFail": { ko: "곡을 추가하지 못했어요.", ja: "曲を追加できませんでした。", en: "Couldn't add the songs.", "zh-Hans": "无法添加歌曲。", "zh-Hant": "無法新增歌曲。" },
  "ytsave.fallbackNote": { ko: "{{reason}} 대신 임시 재생목록으로 들을 수 있어요(내 계정에는 저장되지 않아요).", ja: "{{reason}} 代わりに一時的な再生リストで聴くことができます（アカウントには保存されません）。", en: "{{reason}} You can still listen via a temporary playlist (not saved to your account).", "zh-Hans": "{{reason}} 你仍可通过临时播放列表收听（不会保存到你的账号）。", "zh-Hant": "{{reason}} 你仍可透過臨時播放清單收聽（不會儲存到你的帳號）。" },
  "ytsave.openTempPlaylist": { ko: "임시 재생목록으로 열기 ↗", ja: "一時再生リストで開く ↗", en: "Open temporary playlist ↗", "zh-Hans": "打开临时播放列表 ↗", "zh-Hant": "開啟臨時播放清單 ↗" },

  // ── 프리셋(저장된 플레이리스트) ──────────────────────────────────────────
  "preset.defaultTitle": { ko: "플레이리스트", ja: "プレイリスト", en: "Playlist", "zh-Hans": "播放列表", "zh-Hant": "播放清單" },
  "preset.meta": { ko: "{{time}} · {{n}}곡", ja: "{{time}} · {{n}}曲", en: "{{time}} · {{n}} songs", "zh-Hans": "{{time}} · {{n}} 首", "zh-Hant": "{{time}} · {{n}} 首" },
  "preset.deleteAria": { ko: "프리셋 삭제", ja: "プリセットを削除", en: "Delete preset", "zh-Hans": "删除预设", "zh-Hant": "刪除預設" },
  "time.justNow": { ko: "방금 전", ja: "たった今", en: "just now", "zh-Hans": "刚刚", "zh-Hant": "剛剛" },
  "time.minAgo": { ko: "{{n}}분 전", ja: "{{n}}分前", en: "{{n}}m ago", "zh-Hans": "{{n}} 分钟前", "zh-Hant": "{{n}} 分鐘前" },
  "time.hourAgo": { ko: "{{n}}시간 전", ja: "{{n}}時間前", en: "{{n}}h ago", "zh-Hans": "{{n}} 小时前", "zh-Hant": "{{n}} 小時前" },
  "time.dayAgo": { ko: "{{n}}일 전", ja: "{{n}}日前", en: "{{n}}d ago", "zh-Hans": "{{n}} 天前", "zh-Hant": "{{n}} 天前" },

  // ── 2D 정서 지도(구간별) ─────────────────────────────────────────────────
  "map.nodeVal": { ko: "밝기 {{v}} · 에너지 {{e}}", ja: "明るさ {{v}} · エネルギー {{e}}", en: "Mood {{v}} · Energy {{e}}", "zh-Hans": "明快度 {{v}} · 能量 {{e}}", "zh-Hant": "明快度 {{v}} · 能量 {{e}}" },

  // ── 오마카세 문구 뱅크 ───────────────────────────────────────────────────
  "omakase.time.dawn": { ko: ["차분하게 하루를 여는", "고요한 새벽 감성의"], ja: ["落ち着いて一日を始める", "静かな夜明けの気分の"], en: ["Calmly opening the day", "In a quiet, dawn-colored mood"], "zh-Hans": ["平静地开启一天的", "静谧黎明氛围的"], "zh-Hant": ["平靜地開啟一天的", "靜謐黎明氛圍的"] },
  "omakase.time.morning": { ko: ["상쾌하게 하루를 시작하는", "기운 넘치는 아침"], ja: ["爽やかに一日を始める", "元気いっぱいの朝の"], en: ["Starting the day fresh", "An energetic morning"], "zh-Hans": ["清爽开启一天的", "活力满满的早晨"], "zh-Hant": ["清爽開啟一天的", "活力滿滿的早晨"] },
  "omakase.time.afternoon": { ko: ["나른한 오후를 깨워줄", "집중력 올려주는"], ja: ["けだるい午後を目覚めさせる", "集中力を高めてくれる"], en: ["To wake up a lazy afternoon", "Boosting your focus"], "zh-Hans": ["唤醒慵懒午后的", "提升专注力的"], "zh-Hant": ["喚醒慵懶午後的", "提升專注力的"] },
  "omakase.time.evening": { ko: ["노을 지는 저녁에 어울리는", "하루를 마무리하는 잔잔한"], ja: ["夕焼けの夕方に似合う", "一日を締めくくる穏やかな"], en: ["Fitting a sunset evening", "A mellow close to the day"], "zh-Hans": ["适合晚霞时分的", "为一天画上舒缓句点的"], "zh-Hant": ["適合晚霞時分的", "為一天畫上舒緩句點的"] },
  "omakase.time.night": { ko: ["늦은 밤 감성적인", "잠들기 전 편안한"], ja: ["夜更けの感傷的な", "眠る前の心地よい"], en: ["Sentimental late at night", "Cozy before falling asleep"], "zh-Hans": ["深夜感性满溢的", "睡前放松惬意的"], "zh-Hant": ["深夜感性滿溢的", "睡前放鬆愜意的"] },
  // "맑음(clear)" 날씨 문구 — 시간대 무관 문구(clear)와 낮에만 성립하는 문구(clearDaytime,
  // "햇살"처럼 해가 떠 있어야 말이 되는 표현)를 분리해둔다. omakase.js가 시간대(밤/새벽 제외)에
  // 따라 clearDaytime을 풀에 포함할지 판단한다 — 안 그러면 "햇살 좋은 날씨의 늦은 밤" 같은
  // 모순 조합이 나온다(2026-08-12 버그 리포트).
  "omakase.weather.clear": { ko: ["맑고 청량한"], ja: ["澄んで爽やかな"], en: ["Clear and refreshing"], "zh-Hans": ["清爽晴朗的"], "zh-Hant": ["清爽晴朗的"] },
  "omakase.weather.clearDaytime": { ko: ["햇살 좋은 날씨에 어울리는"], ja: ["日差しの良い天気に似合う"], en: ["Fitting a sunny day"], "zh-Hans": ["适合阳光明媚天气的"], "zh-Hant": ["適合陽光明媚天氣的"] },
  "omakase.weather.cloudy": { ko: ["흐린 날씨에 잔잔한", "구름 낀 하늘 아래 아련한"], ja: ["曇り空に穏やかな", "曇り空の下でせつない"], en: ["Mellow for a cloudy day", "Wistful under an overcast sky"], "zh-Hans": ["阴天里舒缓的", "云层下略带惆怅的"], "zh-Hant": ["陰天裡舒緩的", "雲層下略帶惆悵的"] },
  "omakase.weather.rain": { ko: ["비 오는 날 감성적인", "빗소리와 잘 어울리는"], ja: ["雨の日に感傷的な", "雨音によく合う"], en: ["Emotional on a rainy day", "Pairs well with the sound of rain"], "zh-Hans": ["雨天感性满溢的", "与雨声相得益彰的"], "zh-Hant": ["雨天感性滿溢的", "與雨聲相得益彰的"] },
  "omakase.weather.snow": { ko: ["눈 내리는 날의 포근한", "하얗게 눈 쌓인 겨울 감성의"], ja: ["雪の降る日の温かい", "白く雪が積もった冬の気分の"], en: ["Cozy for a snowy day", "In a snow-covered winter mood"], "zh-Hans": ["雪天暖意融融的", "银装素裹冬日氛围的"], "zh-Hant": ["雪天暖意融融的", "銀裝素裹冬日氛圍的"] },
  "omakase.weather.storm": { ko: ["천둥번개 치는 날 몰입감 있는", "폭풍우 속 강렬한"], ja: ["雷が鳴る日の没入感ある", "嵐の中の強烈な"], en: ["Immersive for a stormy day", "Intense in the middle of a storm"], "zh-Hans": ["雷雨天沉浸感十足的", "暴风雨中强烈震撼的"], "zh-Hant": ["雷雨天沉浸感十足的", "暴風雨中強烈震撼的"] },
  "omakase.suffixes": { ko: ["플레이리스트 만들어줘", "세트리스트 부탁해", "플리 하나 뽑아줘"], ja: ["プレイリスト作って", "セットリストお願い", "プレイリスト1つよろしく"], en: ["make me a playlist", "put together a setlist", "pick me a playlist"], "zh-Hans": ["生成一份播放列表", "拜托来一份歌单", "帮我挑一份歌单"], "zh-Hant": ["產生一份播放清單", "拜託來一份歌單", "幫我挑一份歌單"] },

  // ── 하단 고지(각 언어 1벌만 노출) ────────────────────────────────────────
  "footer.notice1": {
    ko: "* 본 프로젝트는 'BanG Dream!'의 팬이 제작한 비공식 프로젝트이며, 상업적 목적으로 사용되지 않습니다. 사용된 모든 이미지 및 음원의 권리는 ©BanG Dream! Project 및 각 저작권자에게 있습니다.",
    ja: "* 本プロジェクトは『バンドリ！』のファンによる非公式プロジェクトであり、商業目的では使用されません。使用されているすべての画像・音源の権利は©BanG Dream! Project および各権利者に帰属します。",
    en: "* This is a fan-made, non-official project inspired by 'BanG Dream!'. All rights to images and audio belong to ©BanG Dream! Project and their respective owners. This project is for non-commercial use only.",
    "zh-Hans": "* 本项目为『BanG Dream!』粉丝制作的非官方项目，不用于商业目的。所使用的所有图像与音源版权归 ©BanG Dream! Project 及各权利方所有。",
    "zh-Hant": "* 本專案為『BanG Dream!』粉絲製作的非官方專案，不用於商業目的。所使用的所有圖像與音源版權歸 ©BanG Dream! Project 及各權利方所有。",
  },
  "footer.notice2": {
    ko: "* 원하는 분위기를 한 문장으로 입력하면 AI가 뱅드림 곡 데이터를 분석해 무드에 맞는 플레이리스트를 자동으로 만들고 YouTube로 바로 재생합니다. 로그인 없이 모든 기능을 쓸 수 있고, 선택적으로 Google 계정으로 로그인하면 생성된 플레이리스트를 내 YouTube 계정에 실제 재생목록으로 저장할 수 있어요.",
    ja: "* 欲しい雰囲気を一文で入力すると、AIがバンドリの楽曲データを分析してムードに合ったプレイリストを自動生成し、YouTubeですぐに再生します。ログインなしですべての機能が使え、任意でGoogleアカウントでログインすれば生成したプレイリストを自分のYouTubeアカウントに実際の再生リストとして保存できます。",
    en: "* Enter your mood in one sentence and AI builds a matching BanG Dream! playlist from song data, played instantly via YouTube. The app works fully without signing in; optionally, sign in with your Google account to save the generated playlist to your own YouTube account as a real playlist.",
    "zh-Hans": "* 只需用一句话描述你想要的氛围，AI 就会分析 BanG Dream! 曲库数据，自动生成匹配的播放列表并通过 YouTube 立即播放。无需登录即可使用全部功能；也可选择使用 Google 账号登录，将生成的播放列表实际保存为你 YouTube 账号中的播放列表。",
    "zh-Hant": "* 只需用一句話描述你想要的氛圍，AI 就會分析 BanG Dream! 曲庫資料，自動產生匹配的播放清單並透過 YouTube 立即播放。無需登入即可使用全部功能；也可選擇使用 Google 帳號登入，將產生的播放清單實際儲存為你 YouTube 帳號中的播放清單。",
  },
  "footer.ytAttrib": {
    ko: '* 본 서비스는 <strong>YouTube API 서비스</strong>를 이용합니다. 이용 시 <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener">YouTube 서비스 약관</a>이 적용되며, <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google 개인정보처리방침</a>을 함께 참고하세요.',
    ja: '* 本サービスは<strong>YouTube API サービス</strong>を利用しています。利用にあたり<a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener">YouTube利用規約</a>が適用され、<a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Googleプライバシーポリシー</a>もあわせてご確認ください。',
    en: '* This service uses <strong>YouTube API Services</strong>. The <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener">YouTube Terms of Service</a> apply; see also the <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google Privacy Policy</a>.',
    "zh-Hans": '* 本服务使用 <strong>YouTube API 服务</strong>。使用本服务须遵循 <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener">YouTube 服务条款</a>，另请参阅 <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google 隐私权政策</a>。',
    "zh-Hant": '* 本服務使用 <strong>YouTube API 服務</strong>。使用本服務須遵循 <a href="https://www.youtube.com/t/terms" target="_blank" rel="noopener">YouTube 服務條款</a>，另請參閱 <a href="https://policies.google.com/privacy" target="_blank" rel="noopener">Google 隱私權政策</a>。',
  },
  "footer.links": {
    ko: '* <a href="privacy.html">개인정보처리방침</a> <span aria-hidden="true">·</span> <a href="terms.html">서비스 약관</a>',
    ja: '* <a href="privacy.html">プライバシーポリシー</a> <span aria-hidden="true">·</span> <a href="terms.html">利用規約</a>',
    en: '* <a href="privacy.html">Privacy Policy</a> <span aria-hidden="true">·</span> <a href="terms.html">Terms of Service</a>',
    "zh-Hans": '* <a href="privacy.html">隐私权政策</a> <span aria-hidden="true">·</span> <a href="terms.html">服务条款</a>',
    "zh-Hant": '* <a href="privacy.html">隱私權政策</a> <span aria-hidden="true">·</span> <a href="terms.html">服務條款</a>',
  },
};

const I18N = { ko: {}, ja: {}, en: {}, "zh-Hans": {}, "zh-Hant": {} };
for (const key in I18N_TABLE) {
  for (const lang of SUPPORTED_LANGS) {
    I18N[lang][key] = I18N_TABLE[key][lang];
  }
}

let currentLang = (function () {
  try {
    const saved = localStorage.getItem(I18N_STORAGE_KEY);
    if (saved && SUPPORTED_LANGS.includes(saved)) return saved;
  } catch (_) {/* localStorage 불가 시 기본값 사용 */}
  return DEFAULT_LANG;
})();

function t(key, vars) {
  const dict = I18N[currentLang] || I18N[DEFAULT_LANG];
  let str = dict[key] != null ? dict[key] : I18N[DEFAULT_LANG][key];
  if (str == null) return key;
  if (vars) {
    for (const k in vars) str = str.split(`{{${k}}}`).join(String(vars[k]));
  }
  return str;
}

function tArr(key) {
  const dict = I18N[currentLang] || I18N[DEFAULT_LANG];
  return dict[key] || I18N[DEFAULT_LANG][key] || [];
}

// 정적 DOM 텍스트 일괄 적용 — data-i18n(textContent) / data-i18n-html(innerHTML,
// 인라인 태그 포함 문구용) / data-i18n-placeholder / data-i18n-title / data-i18n-aria-label.
function applyStaticI18n() {
  document.documentElement.lang = HTML_LANG_TAG[currentLang] || "ko";
  document.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((el) => { el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel)); });
  document.querySelectorAll("[data-i18n-alt]").forEach((el) => { el.alt = t(el.dataset.i18nAlt); });
}

// 언어 전환 — 정적 텍스트 재적용 + 이미 렌더된 동적 콘텐츠(밴드 목록·트랙리스트·프리셋 등)를
// 가진 다른 모듈에 알려 각자 재렌더하도록 이벤트로 위임한다(이 파일은 다른 모듈을 몰라야 함).
function setLang(lang) {
  if (!SUPPORTED_LANGS.includes(lang) || lang === currentLang) return;
  currentLang = lang;
  try { localStorage.setItem(I18N_STORAGE_KEY, lang); } catch (_) {/* 저장 실패는 무시(세션 내 전환은 정상 동작) */}
  applyStaticI18n();
  document.dispatchEvent(new CustomEvent("i18n:change", { detail: { lang } }));
}

applyStaticI18n();

window.i18n = { t, tArr, setLang, getLang: () => currentLang, SUPPORTED_LANGS };
