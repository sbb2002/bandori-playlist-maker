# 세션 핸드오프 명세서 (토큰 초기화 후 이어받기용)

작성: 부장(메인 세션) · 2026-07-11 · git HEAD `a9c45de` (origin/main 푸시 완료)
목적: 토큰 초기화 후 새 세션이 **이 문서만 읽고 즉시 이어받을 수 있도록** 현재 상태·완료분·
긴급 버그·잔여 백로그·실행법을 정리한다.

---

## 0. 새 세션 시작 체크리스트
1. `git pull` (origin/main 최신). HEAD `a9c45de` 이상인지 확인.
2. `docs/reports/` 최신 보고서 + 본 문서 확인.
3. `python -m pytest src/tests -q` → **68 통과** 기준선 확인.
4. `python src/scripts/verify_quality.py --seeds 12` → **게이트 53/75** 기준선 확인.
5. `.env`(리포 루트 또는 `src/backend/.env`)에 `OPENROUTER_API_KEY` 있는지 확인(없으면 stub 모드).
   모델 기본 `nvidia/nemotron-3-nano-30b-a3b:free`(무료).
6. **최우선: §4 긴급 버그(설정 유지)부터 처리.** 그다음 §5 백로그 순서.

## 1. 현재 상태 (한 줄 요약)
파일럿 앱은 **동작**한다. 자연어 요청 → LLM 무드 해석 → 2단계 선곡(SELECT→SEQUENCE) → 프론트에서
YouTube iframe 순차재생. 무드 매칭·경계 연속성·설정 UI·밴드/커버 필터·비단조 아크·공유까지 구현됨.
남은 건 §4 긴급버그 + §5 백로그(배포·장르 재추출·OAuth).

## 2. 이번 세션에 완료한 것 (커밋 순)
무드 매칭 "조용 요청에 시끄러운 곡" 문제를 **전곡 오디오 재추출**로 근본 해결한 뒤, 검증 체계·
사용자 추가제안을 처리했다.

- **강도(intensity) 재정의** (`repo/song_repo.py`): `Song.energy` = soft-OR(p=3) of
  [`energy_full`(전곡 지각에너지), `−acousticness_proxy` 백분위, `i_min`·`i_mean`·`i_end` 백분위].
  발췌 편향(인트로만 조용한 곡 오판)을 전곡 재추출로 해소. 검증: 灼熱 0.09→0.30, 黒 →0.57,
  Steer to Utopia 0.13→0.48, 栞 0.04. (`docs/research/2026-07-11-full-track-energy-extraction.md`)
- **2단계 엔진 + 경계 연속성** (`domain/selection.py`): Stage A(강도 허용창 하드선택, 밝기버킷+rng
  변주) → Stage B(**이전 곡 아웃트로 ↔ 다음 곡 인트로** 텐션 연속성 다목적 비용 최소화 + 하모닉
  소프트 + 오프너=인트로텐션 최대). 근거: `docs/research/2026-07-11-playlist-sequencing-strategy.md`.
- **프롬프트**(`adapters/prompt.py`): "조용/잔잔"=플랫 저에너지; 활동(유산소 등)=`stage_energies`
  **비단조 아크**(준비↓→본운동↑→정리↓). LLM이 판단(하드코딩 아님).
- **검증 방법론**(R&D): `src/scripts/verify_quality.py`(하네스), `data/ground_truth_labels.csv`(65라벨),
  `docs/research/2026-07-11-verification-methodology.md`(베이스라인·게이트·약점).
- **사용자 추가제안**: #1 누락밴드 eligible(660곡·13밴드) · #2 프롬프트 밴드명 자동필터
  (`api/band_aliases.py`) · #3 Original/Cover 필터 · #4 비단조 아크 · YouTube 공유(watch_videos) ·
  체크박스 동기화(`applied_bands`).
- 회귀 가드 pytest: 무드누출·아크(`test_integration.py`).

## 3. 핵심 파일 맵
- 엔진: `src/backend/app/domain/selection.py`(2단계·연속성·비단조아크), `repo/song_repo.py`(강도 산출).
- LLM: `adapters/prompt.py`(프롬프트·파싱·`stage_energies`), `adapters/openrouter_adapter.py`,
  `adapters/stub_adapter.py`(오프라인).
- API: `api/routes.py`(밴드자동감지·커버필터·`applied_bands`), `api/schemas.py`, `api/band_aliases.py`.
- 프론트: `src/frontend/{index.html,app.js,style.css}`(입력·설정UI·에너지그래프·재생·공유).
- 데이터: `data/songs_master.csv`(660곡, 컬럼 `energy_full`·`i_mean/std/max/min/start/end` 포함),
  `data/full_audio_features.csv`, `data/temporal_intensity.csv`, `data/ground_truth_labels.csv`.
- 추출 스크립트(기기 로컬 오디오 필요): `src/scripts/data/{extract_full_energy,build_energy_full,
  extract_temporal_intensity}.py`. 오디오는
  `../bandori-song-sorter/src/content/cluster/audio_full/{band}__{idx:03d}.wav`(비커밋, 저작물).

## 4. 🔴 긴급 버그 — 요청 간 설정(세부설정) 유지 (UX 치명)
**증상**(사용자 보고): 1차 요청("로젤,라스,마이고… 노래로") 후 2차 요청("몰포 내한공연 세트리스트")을
하면, 1차의 세부설정(밴드 필터 등)이 유지된 채 플리가 생성됨. 2차는 몰포만 기대했으나 1차 밴드가 섞임.

**원인 분석**:
- 프론트 설정 상태가 요청 간 **지속**된다: 밴드 체크박스, Original/Cover 체크박스, 에너지 그래프
  `stageTouched`, target-minutes/stage-count 입력.
- 특히 이번에 추가한 `syncBandChecks(data.applied_bands)`(app.js)가 **자동감지된 밴드를 체크박스에
  고정** → 다음 요청 submit 시 `collectBands()`가 그 체크박스를 그대로 읽어 band_filter로 보냄 →
  거기에 2차 프롬프트 감지분(몰포)까지 합쳐져 밴드가 누적됨.

**권장 수정 방향**(다음 세션 최우선):
- 핵심 원칙: **자연어 요청은 매번 새 의도**다. 프롬프트 자동감지 밴드는 **일회성(per-request)** 이어야
  하고, 사용자가 **수동 체크한 것만 지속**돼야 한다.
- 구현안: 프론트에 `bandsAutoSet` 플래그. `syncBandChecks`(자동) 시 true, 사용자가 체크박스 수동
  토글 시 false. `collectBands()`는 **수동 체크분만** 반환(autoSet이면 [] 반환) → 백엔드가 이번
  프롬프트 감지분을 더함. 결과: 2차 "몰포"는 수동분(없음)+이번감지(morfonica)=morfonica만.
- 함께 검토: 커버 체크박스·그래프(`stageTouched`)도 요청 간 지속됨. 그래프는 "명시 커스터마이즈라
  유지" vs "새 요청이면 리셋"이 설계 결정. 최소한 **자동 동기화된 것**(밴드)은 지속 금지가 맞다.
  대안: "설정 초기화" 버튼 + 새 요청 시 자동감지 오버라이드만 리셋.
- 검증: 1차 밴드요청 → 2차 다른밴드요청 → 2차에 1차 밴드가 안 섞이는지 수동 확인 + API 테스트 추가.

## 5. 잔여 백로그 (우선순위)
1. **[긴급] §4 설정 유지 버그 수정** — 위 방향대로.
2. **#3 파일럿 배포 준비**: 백엔드 호스팅(Render 등, 무료·cold start 허용), 프론트 GitHub Pages,
   `FRONTEND_ORIGIN` CORS 확정(`https://sbb2002.github.io` 예상), umami 커스텀이벤트 3종
   (`playlist_created`·`song_advance`·`playlist_half_played`) + 신규 `playlist_shared` 계측 확인.
   `index.html`의 `SETLIST_API_BASE`를 배포 백엔드 URL로.
3. **#1 장르 재추출**(데이터팀, 기기 오디오 필요): 클럽/파티 미포착 해소. 전곡에서 장르 태그/
   댄서빌리티 추출 → `verify_quality.py`의 `gt_party_frac`를 진짜 장르 지표로 승격.
4. **YouTube 계정저장형 재생목록**(OAuth+Data API): 구글 인증정보 필요. 현재는 익명 watch_videos만.
5. **경계 연속성 심화**(선택): 전역 시퀀싱(TSP류)로 `boundary_gap_max` 축소 — 수확 체감. 현재
   연속성↔하모닉 균형점(`_HARMONIC_PENALTY=0.15`, `_RANDOM_SLACK=0.05`).
6. **[미래 기능] 특정 공연 셋리스트 재현 모드**: "2025-12-24 로젤리아 내한 셋리스트 재현해줘" 류 요청.
   현재 파이프라인(LLM=무드 파라미터만 추출 → 무드 기반 선곡)으로는 **불가** — 사실 검색 + 정확
   매칭이 필요하기 때문. 필요 작업(클린아키텍처: 어댑터1 + 선곡 새 경로):
   - (a) **셋리스트 확보**: OpenRouter `:online` 웹검색(옵션·검색당 유료, 무료 모델도 검색은 유료,
     스펙은 공식문서 확인) **또는 setlist.fm API** 등 **검색 어댑터** 신설(무드 포트와 별개 포트).
   - (b) **정확 매칭 선곡 경로**: 무드 대신 **곡 제목·밴드**를 추출 → 데이터셋에 제목/밴드로 매칭 →
     그 순서대로 구성(무드 아크 무시). 선곡 엔진에 "explicit tracklist" 분기 추가.
   - (c) **커버리지 처리**: 660곡에 없는 공연곡은 누락 표기 또는 유사대체(제목 유사도/동일 밴드).
   파일럿 범위 밖(사실검색·저작권·데이터 커버리지 이슈). 관심 시 별도 티켓으로.

## 6. 검증 방법론 사용법 (모든 엔진 변경 시)
```
python src/scripts/verify_quality.py --seeds 12            # 스코어카드 + 게이트(현재 53/75)
python src/scripts/verify_quality.py --seeds 50 --markdown # 정밀 + 보고표
python src/scripts/verify_quality.py --scenario quiet_calm # 단일 시나리오
```
엔진 변경 전후로 실행해 before/after 비교. 필수 게이트(무드누출·아크)는 pytest로 고정됨 —
회귀 시 실패. 개선추적(경계·하모닉)은 하네스 수치로 추적.

## 7. 알려진 한계 (정직)
- **장르 미포착**: 클럽/파티가 강도 근사(장르 피처 부재). §5-3 재추출로 해소.
- **処救生 잔여**: 전 오디오 피처에서 subdued로 측정(보컬강도는 스펙트럼으로 못 잡음). 문서화된 한계.
- **boundary_gap_max 스파이크**: 상당수는 상승 요청의 **의도된 단계 전환**(순수 결함 아님).
- **watch_videos 공유**: YouTube 익명 재생목록이 이따금 제한/변덕. 안정형은 OAuth(§5-4).
- **연속성↔하모닉 구조적 상충**: 현재 균형점. 한쪽 상향은 다른쪽 하향(결재 사항).

## 8. 환경 / 실행
```
# 백엔드(.env 자동 로드; 키 없으면 stub)
python -m uvicorn app.main:app --app-dir src/backend --port 8000
# 프론트(정적)
python -m http.server 5500 --directory src/frontend
# 테스트
python -m pytest src/tests -q
```
- `.env`: `OPENROUTER_API_KEY`(필수·비커밋), `OPENROUTER_MODEL`(기본 nemotron:free),
  `OPENROUTER_RESPONSE_FORMAT=none`, `FRONTEND_ORIGIN`(배포 시), `MOOD_INTERPRETER`(stub|openrouter).
- 오디오 재추출은 `../bandori-song-sorter/.../audio_full/` 존재 시에만(현재 기기 보유). librosa 사용.
- 참고 논문 PDF(`docs/ref/**/*.pdf`)는 gitignore(로컬 유지). 사용자 의견은 `docs/ref/user-opinion/`.

## 9. 조직/운영 규칙 리마인더
- 부서 개방은 사용자 지시 시(토큰 게이트 R5: 세션≥80%면 신규 스폰 중단). git 커밋·푸시는 부장 전담.
- 데이터팀=`data/`·`src/scripts/`, 코드팀=`src/backend/`·`src/frontend/`·`src/tests/`, R&D=`docs/research/`.
- 각 단계 완료마다 커밋(사용자 요청). 검수 후 origin/main 푸시.

