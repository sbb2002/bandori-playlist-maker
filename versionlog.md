# data 브랜치 Version Log

`main`의 앱 버전(`v1.x.x`, 배포 릴리스 단위)과는 **별개의 독립 버전 체계**다. 이 브랜치는
`data/` 데이터셋 자체의 변경만 기록한다.

## 버전 규칙

| 단위 | 트리거 |
|---|---|
| **Major** | 데이터 구조 또는 컬럼의 전면 개편 (예: 스키마 재설계, 조인 키 변경) |
| **Minor** | 컬럼 추가·제거·편집 (예: 새 파생 지표 컬럼 추가) |
| **Patch** | 신곡 추가 |

## 작성 규칙

매 항목에 다음을 남긴다:
- **버전**(`vX.Y.Z`)
- **날짜시각**(`YYYY-MM-DD HH:MM`, KST)
- **작업내역**: 무엇이 바뀌었는지 + **현재 총 곡 수**(`data/songs_master.csv` 기준, 상시 표시)
- **Patch(신곡 추가)인 경우**: 추가된 각 곡의 `band`·`song`·`url`을 전부 나열한다.

## Log

### v1.2.1 — 2026-08-18 (Patch)

`various_artists` 나머지 4곡의 `display_band`를 YouTube 발매 메타데이터(℗
레이블·아티스트 크레딧)로 확인해 채움 — `main` PR #87(`v2.7.1`)이 곡 추가
팝업에서 이 콜라보곡들이 `various_artists` 밖으로 튀어나와 보이던 버그를
고치면서 함께 반영.

- 현재 총 곡 수: **734곡** (변동 없음, 컬럼 값만 채움)
- idx=101 `Don't be afraid!`, idx=102 `Glee! Glee! Glee!` → `display_band=Glitter*Green`
- idx=103 `Be shine, shining!` → `display_band=CHiSPA`
- idx=104 `Here, the world` → `display_band=sumimi`
- idx=105 `CiRCLE THANKS MUSiC♪`는 7개 밴드(Poppin'Party·Afterglow·Pastel*Palettes·
  Roselia·Hello Happy World·Morfonica·RAISE A SUILEN) 합동곡이라 단일
  display_band로 특정할 수 없어 빈 값 유지(various_artists 그대로 표시).

### v1.2.0 — 2026-08-18 (Minor)

`songs_master.csv`에 신규 컬럼 `display_band` 추가(모든 행 기본값 빈 문자열).
`band`(필터·통계용 원본 소속)와 분리된 "재생 시 표시용 밴드명" 필드 — `main`
`feature/display-band`(PR #86, `v2.7.0`)가 이 컬럼을 읽어 세트리스트 결과·곡
추가 화면에 노출한다.

- 현재 총 곡 수: **734곡** (변동 없음, 컬럼만 추가)
- **RAISE A SUILEN "THE THIRD(仮)" 12곡** → `band=various_artists`,
  `display_band=THE THIRD(仮)`로 재분류. RAS 결성 이전 임시 유닛 명의로 다른
  밴드(Poppin'Party·Pastel*Palettes·Hello Happy World·Roselia) 곡을 라이브
  커버한 것으로, 참여 인원 구성이 현재 RAS와 다르므로 별도 유닛으로 취급하기로
  결정(idx 516,517,518,519,520,521,522,523,524,526,527,729). RAS 자체 선곡
  풀에서는 제외되지만 재생 목록엔 "THE THIRD(仮)"로 표시된다.
- **YouTube API 전수조사로 곡명에 `(Cover)`/`(Solo)`/`(feat. X)` 태그 정정** —
  실제 발매 아티스트·채널 메타데이터(`℗` 저작권 라벨, 업로드 채널) 대조 기준:
  - `mugendai_mutype` idx=691 `好きになっちゃえ！` — 이전 세션 백필 오류(Neko
    Hacker 원곡에 멤버가 게스트 참여한 곡을 자체곡으로 오분류) 정정,
    `(feat. 仲町あられ)`로 수정.
  - `mugendai_mutype` 그 외 44곡: 개인 채널 솔로 커버는 `(Solo)`(32곡), 峰月律
    채널 중 원제목에 영문 `(Cover)`가 그대로 있던 5곡은 `(Cover)` 유지,
    그룹 일부 멤버만 참여한 6곡은 `(feat. 참여 멤버)`, 그룹 전원 참여지만
    자기 밴드 명의 곡이 아닌 3곡은 `(Cover)`.
  - `poppin_party` 개인 캐릭터 공식 솔로곡 5곡 → `(Solo)`.
  - `mygo` 개인 채널 "歌ってみた" 단독 커버 16곡 → 기존 `(Cover)` 오표기를
    `(Solo)`로 정정(개인 참여 + 원제목에 영문 `(Cover)` 표기 없음).
  - `raise_a_suilen` "THE THIRD(仮)" 12곡 → `(Cover)`(위 재분류와 별개로 곡명에도 표기).
  - `afterglow`·`hello_happy_world`·`morfonica`·`pastel_palettes`·`ave_mujica`는
    기존 `(Cover)` 표기가 이미 규칙과 일치해 수정 없음.
  - `roselia` idx=731 `擬態ごっこ (Cover)`(Sakamata Chloe 콜라보)는 참여 인원
    메타데이터 확인 불가로 보류(추후 확인 필요).

### v1.1.0 — 2026-08-02 19:31 (Minor)

`songs_master.csv`에 9개 신규 오디오 지표 컬럼 추가(`bpm-research` 연구
`topic/20260731_audio_feats_revised/report_final.md` 최종 채택분): `m3-mode`,
`m4-lufs_integrated`, `m4-lra`, `m5-arousal_median`, `m6-valence_median`,
`m7-danceability_norm`, `m8-acoustic_median`, `m9-instr_stem_ratio`,
`m11-speech_median`. 기존 컬럼·행은 전혀 건드리지 않고 끝에 추가만 함(순수
additive) — `main` 배포판(`song_repo.py`)은 이름으로 필요한 컬럼만 읽으므로
영향 없음(직접 로드 테스트로 확인).

- 현재 총 곡 수: **732곡** (변동 없음, 컬럼만 추가)
- 앱(`bandori-playlist-maker`) 쪽 반영은 아직 "배관"만 돼 있고(요청/응답 왕복만),
  선곡 엔진 가중치엔 미반영 — `epic/improved-playlist-maker` 브랜치에서 진행 중.
- 값 중 `m4-lufs_integrated`·`m4-lra`·`m5-arousal_median`·`m6-valence_median`·
  `m9-instr_stem_ratio`·`m11-speech_median`은 아직 **원시값**(0~100 백분위
  변환 전) — 정규화는 추후 앱 쪽에서 처리 예정.
- 신곡 반영 시 이 9개 중 가벼운 3개(`m4-lufs_integrated`·`m4-lra`·
  `m7-danceability_norm`)는 `tools` 브랜치 `run_autoloader.py`가 자동으로
  채우고, 무거운 3개(`m5-arousal_median`·`m6-valence_median`·
  `m9-instr_stem_ratio`·`m11-speech_median`... 실제로는 valence·
  instr_stem_ratio·speech_median 3개)는 `data/enrich_heavy_feats.py`(WSL2
  전용, 반자동)로 별도 주기 보강. `m3-mode`·`m8-acoustic_median`은 신곡
  반영 로직에 아직 미배선(범위 밖).

### v1.0.6 — 2026-07-31 20:09 (Patch)

오토로더 신곡 자동 반영 2곡.

- 현재 총 곡 수: **732곡** (이전 730곡)
- 추가 곡 목록(band·song·url):
  - mugendai_mutype / Face The Next — https://youtu.be/6PpzqcesklA
  - mugendai_mutype / TearJerker — https://youtu.be/T8ynAJWmPtM

### v1.0.5 — 2026-07-26 16:50 (Patch)

오토로더 신곡 자동 반영 43곡(커밋 `c0e0249`). 이번 반영 직전, 두 가지 파이프라인
버그를 발견·수정했다(상세는 `BACKFILL_STATUS.md` 참고):
(1) 형제 `bandori-song-sorter`의 `audio_map.json` 배열 위치-idx 정합성 붕괴
(해당 저장소 PR #11로 수정), (2) 이 저장소 `merge_data.py`가 master idx를
형제 idx에서 그대로 복사해 쓰던 설계 결함(형제측 idx 전역 재정렬 시 기존 곡과
충돌 가능 — `tools` 브랜치 PR #59로 master 자체 채번 방식으로 수정). 두 수정
모두 머지 후 이번 반영이 43/43 성공했다.

- 현재 총 곡 수: **730곡** (`data/songs_master.csv`, 이전 687곡)
- 추가 41곡은 2026-07-26 세션의 수동 백필 재검증 결과(비mutype 3+mutype 38,
  `BACKFILL_STATUS.md` 참고), 나머지 2곡(raise_a_suilen·roselia)은 형제
  저장소의 별도 자동감지로 동시에 잡힌 신곡.
- 추가 곡 목록(band·song·idx·video_id):
  - morfonica / 深海少女 (Cover) (idx=689, 8McGbxeGqdY)
  - mugendai_mutype / 等身大あんりみてっど (idx=690, XbqG3T4MGJE)
  - mugendai_mutype / 好きになっちゃえ！ (idx=691, mhmXN1uZTzE)
  - mugendai_mutype / YoU kNOw the overture (idx=692, UWHzX6SpizM)
  - mugendai_mutype / 君が飛び降りるのならば (Cover) (idx=693, BI71vana4VI)
  - mugendai_mutype / 地球最後の告白を (Cover) (idx=694, 7R1DMU0qa00)
  - mugendai_mutype / パラレルラルラ (Cover) (idx=695, ZcY2a1DyVAo)
  - mugendai_mutype / 夜もすがら君想ふ (Cover) (idx=696, OsJPJo4uKBc)
  - mugendai_mutype / ジレンマ (Cover) (idx=697, 3M5YaHlpMjY)
  - mugendai_mutype / glow (Cover) (idx=698, WS4flpVYkLg)
  - mugendai_mutype / メンタルチェンソー (Cover) (idx=699, eI-BW0Bcq4g)
  - mugendai_mutype / ホシアイ (Cover) (idx=700, d6n4WHEtAgE)
  - mugendai_mutype / フォニイ (Cover) (idx=701, 0makuFTnChs)
  - mugendai_mutype / ELECT (Cover) (idx=702, uaAIGOd9Qv0)
  - mugendai_mutype / ユキトキ (Cover) (idx=703, LXYyBjnbQys)
  - mugendai_mutype / スイートマジック (Cover) (idx=704, PsPtBzaevyA)
  - mugendai_mutype / 少年よ我に帰れ (Cover) (idx=705, 2TtYsm1HDx8)
  - mugendai_mutype / One Last Kiss (Cover) (idx=706, fyc4aGZ9C18)
  - mugendai_mutype / ミルククラウン・オン・ソーネチカ (Cover) (idx=707, yHMLvqxh2PQ)
  - mugendai_mutype / 決戦スピリット (Cover) (idx=708, i-cgqBosaDw)
  - mugendai_mutype / ティアドロップス (Cover) (idx=709, gZe2UGwld2E)
  - mugendai_mutype / ロウワー (Cover) (idx=710, FhaynKrmQro)
  - mugendai_mutype / ハイドアンド・シーク (Cover) (idx=711, FvLSUJ35qmE)
  - mugendai_mutype / 不可解 (Cover) (idx=712, YHfBJMxWSec)
  - mugendai_mutype / GURU (Cover) (idx=713, D7M1eAnroZE)
  - mugendai_mutype / 経験値上昇中☆ (Cover) (idx=714, e15grxDKfF8)
  - mugendai_mutype / 翼をください (Cover) (idx=715, RGByUSGhQgE)
  - mugendai_mutype / 元気を出して (Cover) (idx=716, RzgsdgCkFjU)
  - mugendai_mutype / ハッピー☆マテリアル (Cover) (idx=717, yLj0VCQC8qE)
  - mugendai_mutype / 時をかける少女 (Cover) (idx=718, XEzZRDCZBSc)
  - mugendai_mutype / TOMORROW (Cover) (idx=719, _WXK_IB4cck)
  - mugendai_mutype / PARTY☆NIGHT（D-POP version） (Cover) (idx=720, tdZgnk1nEG4)
  - mugendai_mutype / CH4NGE (Cover) (idx=721, ivfYQxQBiXQ)
  - mugendai_mutype / 絶え間なく藍色 (Cover) (idx=722, bLIW2klD4Ms)
  - mugendai_mutype / 撫でんな (Cover) (idx=723, tZzToEEZjgo)
  - mugendai_mutype / なにやってもうまくいかない (Cover) (idx=724, 9Ba8G_i4dAg)
  - mugendai_mutype / マーシャル・マキシマイザー (Cover) (idx=725, Gc7vzpnIYSU)
  - mugendai_mutype / ZEAL of proud (Cover) (idx=726, 4MPXhnbf29o)
  - mugendai_mutype / 繰り返し一粒 (Cover) (idx=727, xjGwcPHPAo8)
  - poppin_party / 乙女はサイコパス (Cover) (idx=728, pFNrfao3dXg)
  - raise_a_suilen / R・I・O・T (idx=729, NTkFFLOLuCc)
  - roselia / Neo-Aspect (idx=730, Izq3AAix1Os)
  - roselia / 擬態ごっこ (Cover) (idx=731, -3HDhazL-FA)

### v1.0.4 — 2026-07-25 (Patch, 소급 기록)

오토로더 신곡 자동 반영 16곡(커밋 `954b2ae`) — mygo 개인 멤버 솔로 커버.
이 로그가 당시 갱신되지 않아 소급 기록한다.

- 현재 총 곡 수: **687곡**
- 추가 곡 목록(band·song·idx·video_id):
  - mygo / 二息歩行 (Reloaded) (idx=673, q7lbzmTw8RM)
  - mygo / 社会距離 (idx=674, Y5qJcXd0two)
  - mygo / 君の神様になりたい。 (idx=675, HwLbvP99ypk)
  - mygo / Henceforth (idx=676, Lr-bMZ2hNH0)
  - mygo / ティアドロップス (idx=677, 3KVLbAMPwzs)
  - mygo / 遠心力 (idx=678, 9RNcp7rLecQ)
  - mygo / ないばいたりてぃ (idx=679, tAZGnS1FKRE)
  - mygo / キリトリセン (idx=680, 3fBftYWm8gY)
  - mygo / もしも命が描けたら (idx=681, uVGIGeTPQVM)
  - mygo / TEENAGE RIOT (idx=682, Hm90Otiz8u8)
  - mygo / パメラ (idx=683, wbbcQokPgLM)
  - mygo / 栞 (idx=684, 3ye4lnEsJRY)
  - mygo / シンデレラボーイ (idx=685, SKyIh9ddvck)
  - mygo / 少女レイ (idx=686, DEXX5zBkRjQ)
  - mygo / 正しくなれない (idx=687, azECAVAWRxI)
  - mygo / 恋してる自分すら愛せるんだ (idx=688, swsu_JBv6Ug)

부수: 이후 커밋 `ea1038d`(mutype·mygo 24곡)·`4dd9374`(Roselia·Pastel·Afterglow·
Poppin'Party 25곡)에서 `(Cover)` 접미사 누락 버그를 수정(신곡 추가 아니라 기존
행 텍스트 정정이라 곡 수 변동 없음 — 687곡 유지, 별도 버전 번호 부여 안 함).

### v1.0.3 — 2026-07-25 (Patch, 소급 기록)

오토로더 신곡 자동 반영 8곡(커밋 `d4dac7c`) — 무겐다이 뮤타입 밴드 합동 커버.
이 로그가 당시 갱신되지 않아 소급 기록한다.

- 현재 총 곡 수: **671곡**
- 추가 곡 목록(band·song·idx·video_id):
  - mugendai_mutype / 唱 (idx=665, zVdR0urFjnc)
  - mugendai_mutype / インキャのキャキャキャ (idx=666, _jU3f42nbGs)
  - mugendai_mutype / デビルじゃないもん (idx=667, y-kKg3F7-TA)
  - mugendai_mutype / エイリアンエイリアン (idx=668, QmYpqqTvVHc)
  - mugendai_mutype / ぼくたちいつでも しゅわっしゅわ！ (idx=669, dvmoFIxT6D4)
  - mugendai_mutype / 回レ!雪月花 (idx=670, Nq2Sl4Ba44M)
  - mugendai_mutype / ビッグマウス feat.りむる (idx=671, i7vyrp_3an0)
  - mugendai_mutype / KiLLKiSS (idx=672, n4AUKXIjNeo)

### v1.0.2 — 2026-07-20 12:05 (Patch)

오토로더 신곡 1곡 반영(커밋 `4945309`, 서브 로컬 `--soft` 실행 — 단, `intensity_norm.json`
동결 상수가 이미 있어 폴백 미발동, `i_*` 포함 전 지표 실측 산출·provisional 없음).

- 추가 곡: `ikka_dumb_rock` · Keep on Riddim · https://youtu.be/h0QJo5XjosA
- 현재 총 곡 수: **663곡** (`data/songs_master.csv`)
- 부수: `shape_norm.json` 워크트리 잔존 사본(07-16 재빌드, 663곡 기준 — 동결 원칙 위반)을
  폐기하고 커밋본(07-15, 원시 660곡 기준)으로 정리.

### v1.0.1 — 2026-07-19 01:48 (Patch, 소급 기록)

오토로더 신곡 1곡 반영(커밋 `9b4ebb9`). 반영 당시 이 로그가 갱신되지 않아 소급 기록한다.

- 추가 곡: `millsage` · カーネーションの咲く日に · https://youtu.be/-CFoE43oPOk
- 현재 총 곡 수: **662곡**

### v1.0.0 — 2026-07-16 (baseline)

브랜치 재편(`data/` 외 전 파일 제거, `main` 스냅샷 잔재 정리) 시점의 데이터셋 스냅샷을
이 독립 버전 체계의 기준점으로 삼는다. 이전 이력(658곡 마스터 구축 → 3곡 자동 추가)은
git 커밋 로그(`git log -- data/songs_master.csv`)로 추적 가능하나, 이 버전 로그 자체는
여기서부터 시작한다.

- 현재 총 곡 수: **661곡** (`data/songs_master.csv`)
- 파일 구성: `songs_master.csv`(canonical) · `songs_full.csv` · `song_features_with_proxies.csv` ·
  `full_audio_features.csv` · `temporal_intensity.csv` · `audio_map.json` ·
  `feature_norms.json` · `energy_full_norm.json` · `intensity_norm.json` ·
  `legacy/`(구버전 스냅샷 2종)
