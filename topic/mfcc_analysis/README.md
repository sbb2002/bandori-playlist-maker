# MFCC 음색 탐색 (research/mfcc-timbre)

## 배경·목적

`research/mood-warmth-feature`에서 "가련/애절(pathos)"을 잡으려다, 현재 선곡 파라미터
(brightness=mode_score, energy)로는 지각의 대부분이 미설명이라는 결론에 도달했다. 그 후속으로,
**"가련/애절"을 넘어 더 다양한 감정 단어를 포착하는 feature를 넓힐 수 있는지**를 확인하기 위한
정성(定性) 탐색이다. 통계 검증(사전등록)이 아니라 **눈으로 스캔**하는 단계 — MFCC라는 표준
음색 지문을 밴드·곡별로 펼쳐 놓고, 감정/음색 차이가 시각적으로 갈라지는지, 그 차이가 **편곡
(반주)에서 오는지 보컬 발성에서 오는지**를 raw vs vocal 대비로 먼저 본다.

MFCC로 알 수 있는 것: 낮은 계수(1~2)=스펙트럼 기울기(밝기/음색 포락선), 중간 계수(3~7)=포먼트
(모음·악기 공명), 높은 계수=미세 질감(치찰음·거칠기). 시간축 변화를 보면 곡 진행에 따른 음색
궤적이 보인다. **비지도 feature라 감정 라벨을 자동으로 말해주진 않는다** — 여기선 곡을 아는
사람이 패턴을 보고 가설을 세우는 용도다. 정량 검증은 다음 라운드(라벨링→상관)에서.

## 데이터·표본

- 곡 세트: `data/songs_full.csv`의 13밴드 중 컴필/단곡 태그 3종(various_artists·ikka_dumb_rock·
  millsage) 제외 → **10밴드 × 각 3곡 = 30곡**. 밴드별로 idx 오름차순 첫 3곡(결정론적, `select_songs.py`).
- 오디오: 형제 프로젝트 `bandori-song-sorter`의 `audio_full/` 로컬 캐시 재사용(21곡). 로컬에 없던
  poppin_party·roselia·raise_a_suilen 9곡은 `download_missing.py`(yt-dlp)로 받아 wav 변환
  (ffmpeg 미설치라 `imageio_ffmpeg` 바이너리로 webm→모노 48kHz wav).
- 보컬 분리: Demucs `htdemucs` two-stems(`separate_vocals.py`) → 30/30 `vocals.wav`.

## 산출물

- `fig/mfcc/<band>_mfcc.png` — 밴드당 1장, **2×3 레이아웃**: 위=raw mix, 아래=vocal-only,
  가로=밴드의 3곡. **2차 개정(CQT)**: MFCC 계수(quefrency 도메인, 주파수 아님)는 음계로
  변환할 수 없다는 게 드러나 `plot_mfcc.py`를 **CQT(Constant-Q Transform)**로 전면 교체.
  y축은 실제 음계(C2~C7, `y_axis="cqt_note"`), 컬러는 발산형(coolwarm) 대신 dB 크기 기준
  순차 컬러맵(`magma`, 어두움=조용함·밝음=큼)으로 가독성 개선. 현재 mygo·ave_mujica 2밴드
  (6곡)만 CQT로 재생성 완료, 나머지 8밴드는 아직 구버전 MFCC 이미지 — 전체 재생성은 미착수.
- `fig/melody/<band>_melody.png` (신규) — vocal 스템에서 `librosa.pyin`으로 단선율 f0 궤적을
  뽑아 시간×음계 라인 그래프로 표시(`plot_melody.py`). CQT보다 "악보에 가까운" 형태로 멜로디
  라인만 보고 싶을 때 사용. **주의**: pyin은 옥타브 오탐지·화음/코러스 구간에서 스파이크가
  생길 수 있어 후처리(median filter, 옥타브 보정) 없이는 정밀 채보로 못 씀. 현재 mygo·
  ave_mujica 6곡만 생성.
- `fig/cqt_preview/<band>_cqt_preview.png` (신규, 임시) — 로컬 캐시 21곡(다운로드·보컬분리
  불필요)만으로 raw-mix CQT 방향성을 빠르게 검증한 미리보기. 정식 산출물이 아니라 설계 확인용.
- `combined_metrics.csv` (30행) — 곡별 지표 통합(`extract_metrics.py`):
  - **기존 지표**(앱이 쓰는 것, `data/song_features_with_proxies.csv`에서): mode_score·energy_proxy·
    acousticness_proxy·instrumentalness_proxy·harmonic_ratio·voiced_frac_mix·tempo_excerpt·key.
  - **연구 지표**(mood-warmth 보컬 발성 계열, vocal 스템에서 재계산): jitter_local·shimmer_local·
    hnr_mean·f0_median_st·f0_range_st·f0_std_st·vocal_ratio·vocal_centroid.
- `fig/metrics/<metric>.png` — 지표별 밴드색 가로 막대(30곡, `plot_metrics.py`). 밴드 경향이
  갈라지는지 정성 스캔용.

### 환경 이슈 — torchaudio/torchcodec (2026-07-16 발견)

이 conda 환경의 `torchaudio`(2.11)가 `torchaudio.load`/`save`에 `torchcodec` 설치를 강제
요구하는데, `demucs` 4.0.1은 `RuntimeError`만 잡고 torchcodec의 `ImportError`/`OSError`는
못 잡아서 `python -m demucs`가 그대로 죽는 버그가 있음. `_demucs_run.py`(신규)가
`torchaudio.load`/`save`를 soundfile 기반 함수로 몽키패치한 뒤 `demucs.separate.main()`을
인프로세스로 호출하는 우회 러너 — `separate_vocals.py`가 `python -m demucs` 대신 이걸 사용하도록
수정함. 재현 시 이 환경 문제를 다시 마주치면 이 파일을 참고.

또한 `LOCAL_AUDIO_DIR` 경로가 예전 머신 기준(`C:\Users\user\...\myprojects\...`)으로 하드코딩돼
있었는데, 실제로는 `C:\Users\User\Documents\pyworks\bandori-song-sorter\...`라 깨져 있었음 —
`plot_mfcc.py`·`separate_vocals.py` 둘 다 수정함.

`plot_mfcc.py`/`plot_melody.py`/`separate_vocals.py` 모두 밴드 이름을 CLI 인자로 주면 일부만
처리 가능(`python plot_mfcc.py mygo ave_mujica`) — 전체 30곡 대신 샘플만 빠르게 재생성할 때 사용.

## 재생성 순서

```
cd topic/mfcc_analysis   # 오디오 스택 env(librosa/parselmouth/demucs/matplotlib)
python select_songs.py         # 30곡 선정 → selected_songs.csv
python download_missing.py     # 로컬에 없는 곡만 yt-dlp 다운로드 → audio_dl/
python separate_vocals.py      # demucs 보컬 분리 → stems/  (곡당 ~1–2분)
python plot_mfcc.py            # raw/vocal MFCC 2×3 → fig/mfcc/
python extract_metrics.py      # 지표 통합 → combined_metrics.csv  (pyin이라 느림)
python plot_metrics.py         # 지표 막대 → fig/metrics/
```

대용량 바이너리(`stems/`·`audio_dl/`·`*.wav`)는 `.gitignore`로 제외 — 위 순서로 재생성 가능.

## 관찰 (정성, 잠정)

- MFCC 0번 계수를 빼고 robust 스케일로 바꾸자 raw의 음색 텍스처와 vocal의 발성 활동 구간
  (유성/무음)이 뚜렷해졌다. 밴드·곡 간 패턴 차이를 눈으로 스캔할 수 있는 상태.
- raw vs vocal 대비의 값: 같은 곡이라도 raw에서 두드러지는 색(반주 편곡 특성)과 vocal에서만
  보이는 발성 질감이 분리돼, "이 인상이 편곡에서 오는지 창법에서 오는지"를 눈으로 구분 가능.

### 2차 관찰 — CQT/멜로디 샘플 (mygo vs ave_mujica, 2026-07-16)

- CQT(음계축)+magma로 바꾸니 raw는 반주의 저역 두께, vocal은 곡 구조(절/후렴/간주의 무음 구간)가
  MFCC 버전보다 훨씬 직관적으로 보임. mygo 迷星叫는 간주 구간이 뚜렷이 비고, ave_mujica KiLLKiSS는
  도입부 무음 후 저역이 한번에 차는 구조가 raw/vocal 양쪽에서 다 확인됨.
- `combined_metrics.csv`의 f0 지표로 두 밴드를 정량 비교: 중심 음높이(median)는 두 밴드가
  F#4~G#4로 거의 동일, 그러나 **ave_mujica가 음역폭(f0_range, 특히 KiLLKiSS 33.8st)·피치
  변동성(std)·vocal_ratio 모두 더 큼** — "더 극적으로 보컬을 쓴다"는 인상과 방향은 일치.
  다만 harmonic_ratio·tempo_excerpt·energy_proxy는 밴드 간 유의미한 차이가 없어, 사용자가
  느끼는 "heavy metal vs emo-funk" 장르 인상(악기 편성·리듬/그루브 문제)은 지금 가진 어떤
  feature로도 설명이 안 됨 — **음향 feature가 설명하는 건 보컬 표현의 극적임 정도까지고,
  장르감 자체는 못 짚는다**는 한계가 재확인됨.
- pyin 멀로디 라인 추출(`plot_melody.py`)은 CQT보다 더 "채보에 가까운" 형태로 보컬 궤적을
  보여주지만, 옥타브 오탐지·스파이크가 섞여 있어 정밀 채보로 쓰려면 후처리가 필요함.
- **사용자 코멘트(가장 중요한 시사점)**: 迷星叫와 Georgette Me, Georgette You를 실제로 들으면
  느껴지는 감정 차이가 음향 지표(피치 서스펜션이 있고 흔들림이 적은데도 인상이 다름)로는 설명이
  안 된다는 지적 — 가사(의미 층위)가 이 잔차를 설명할 핵심 축일 수 있다는 가설이 나옴.

## 다음 단계 아이디어 (미착수, 실험적)

사용자 직감: `감정 ≈ w_가사 × 가사감정벡터 + w_음향 × 음향감정벡터` 형태의 가중합/late-fusion이
현재 잔차(가사 없이는 안 잡히는 감정 차이)를 설명할 수 있지 않겠냐는 가설. MIR 분야의 멀티모달
감정 인식 흐름과 방향이 일치하지만, 실행하려면:

- **가사 DB화 금지, 임베딩으로만 사용**: 가사 원문을 텍스트 DB로 저장하는 건 저작권 리스크가
  있음 — 대신 가사를 감정 임베딩(예: LLM 기반 감정 벡터 추출, 이 프로젝트가 이미 쓰는 OpenRouter
  재사용 가능)으로만 변환해 보관하는 방향이 사용자가 제안한 완화책.
- **일본어 감성사전/모델**: 영어권 도구(VADER 등)는 일본어에 안 맞음 — 일본어 전용 감성사전이나
  LLM 감정 추출이 필요.
- **음향 쪽도 hand-crafted 통계(f0/jitter/HNR 등) 대신 임베딩 검토**: 지금까지의 저차원 통계가
  한계에 부딪힌 걸 보면, 곡 전체 오디오(또는 이번에 뽑은 모든 통계량)를 사전학습 오디오 임베딩
  (예: emotion2vec류)이나 통계량 자체를 벡터화해 쓰는 게 더 풍부한 표현일 수 있음 — 사용자가
  "음향학적으로 이 음원에서 추출한 모든 통계량을 임베딩으로 변환"하는 방향도 제안.
  가사 임베딩과 음향 임베딩 두 갈래를 모두 실험 후보로 열어둠.
- **가중치(w) 추정**은 결국 라벨링된 감정 평가 데이터가 있어야 함 — 이미 계획된 "다음 라운드
  (감정 단어 라벨링)"가 그 데이터가 될 수 있음.

### 화성(코드) 진행 탐색 — 샘플 (2026-07-16)

`chord_estimate_sample.py`(신규, 미커밋 아님 — 다음 커밋에 포함) — 크로마(`chroma_cqt`) +
장/단 3화음 템플릿 매칭 + median filter 스무딩으로 **근사** 코드 진행을 뽑는 탐색용 스크립트.
전용 코드 인식 모델(madmom 등)은 이 환경에 없어 정밀도는 낮음 — 특히 **장조/단조 템플릿이
근음·5도가 같고 3도만 달라 서로 오분류되기 쉬움**(예: Db장조가 C#m으로 잘못 잡힘)이 실제
샘플에서도 확인됨(`ref/mygo_score.png`의 실제 악보 조표(Ab장조/F단조 4플랫)와 대조해 검증).

**키+화성범위만으로 판단 가능한 것(정리)**:
1. 장/단조(mode) — 기존 `mode_score`와 동일 축, 새 정보 아님.
2. **화성 어휘 크기**(곡에서 쓰는 서로 다른 코드 수) — mygo 迷星叫는 Ab/Fm/Db 소수 코드 반복
   (그루브 중심), ave_mujica KiLLKiSS는 E/Em/C/G/D/B/F#m 등 훨씬 다양 — 소수 반복↔다양성 축.
3. **조성 이탈 정도**(다이어토닉 안에 머무는지 vs 차용화음/전조로 벗어나는지) — ave_mujica가
   원조(E) 밖의 "먼" 코드(C·G·D)를 자주 씀. **차용화음/조성 이탈은 음악이론적으로 "애틋함/
   씁쓸함" 지각과 자주 엮이는 클리셰라, mood-warmth 1차 연구의 가련/애절 미제 잔차를 설명할
   후보 축으로 유력** — 다음 라운드 feature 후보에 추가할 만함.
4. **화성 리듬**(코드 변화 빈도, 템포와 별개) — ave_mujica 125~140초처럼 8초 간격으로 자주
   바뀌면 "급박/긴장", mygo처럼 코드 하나를 오래 붙잡으면 "정체/그루브".

**못 짚는 것**: 악기 편성(디스토션 등 음색)·리듬 패턴(싱커페이션/펑키함) — 화성이 아니라 별도
축이라 여전히 다른 feature 필요.

### Whisper 기반 가사 임베딩 + 음향 임베딩 결합 아이디어 (사용자 제안, 2026-07-16, 미착수)

정형화된 방법이 없는 상태이니 아예 새로운 접근을 시도해보자는 제안:

1. 분리된 vocal 스템에 **Whisper**로 ASR을 돌려 가사 텍스트를 추출한다(정확도는 일단 감수).
2. 반복되는 가사 패턴을 찾아 intro/verse/chorus 등 곡 구조를 구분한다 — 또는 그냥 전체
   가사를 통째로 쓴다(단순화 옵션).
3. 그 가사(구조별 또는 전체)를 **감성 임베딩**으로 변환한다.
4. 지금까지 뽑은 음향학적 통계(f0/화성/HNR 등)도 별도의 **음향 감성 임베딩**으로 변환한다.
5. 두 임베딩을 결합해, 사용자의 자연어 프롬프트와 결이 같은 곡을 추론(유사도 매칭)한다.

**보완이 필요한 점**:

- **저작권 재확인**: Whisper 출력도 결국 가사 원문의 (부정확할 순 있어도) 사실상의 사본이다.
  앞서 나온 "원문 DB화 금지" 원칙이 여기도 그대로 적용돼야 함 — **ASR 결과 텍스트를 디스크/DB에
  영속 저장하지 말고, 임베딩 변환 후 원문은 즉시 폐기**하는 파이프라인으로 설계해야 함.
- **노래 음성 ASR 정확도**: Whisper는 대화체 음성 위주로 학습돼 있어 **가창(특히 멜리스마·
  샤우팅·비브라토)에서는 WER(단어 오류율)이 크게 오른다**고 알려져 있음 — 보컬 분리 스템을
  넣어도 순수 대사보다 낮은 정확도를 각오해야 함. 오류가 심하면 임베딩에도 노이즈로 전파됨.
- **환각(hallucination) 위험**: Whisper는 무음/반주만 있는 구간에서 있지도 않은 텍스트를
  생성하는 경우가 보고돼 있음 — 무보컬 구간(간주 등, 이번 CQT/멜로디 분석에서 이미 확인된
  무음 구간)을 사전에 걸러내고 넣는 게 안전함.
- **가사 반복 기반 구조 분할의 한계**: ASR 오류 때문에 같은 후렴이 매번 다르게 전사될 수 있어
  텍스트 반복 매칭만으로는 chorus 탐지가 불안정할 수 있음 — 오디오 자기유사도(self-similarity
  matrix, 크로마/MFCC 기반, `librosa.segment` 등)로 구조를 잡고 가사는 보조로 쓰는 편이 더
  안정적일 수 있음. 순수 반주 구간(간주·솔로)은 애초에 가사가 없어 가사 기반 분할만으로는
  커버 불가 — 오디오 기반 분할이 필수적으로 보완돼야 함.
- **일본어 감성 임베딩 모델 선택**: 영어 중심 임베딩보다 다국어/일본어 지원 임베딩(또는 이
  프로젝트가 이미 쓰는 OpenRouter LLM으로 감정 벡터화)이 적합할 가능성.
- **사용자 프롬프트와의 매칭 공간 정합**: PRD상 이미 LLM으로 사용자 프롬프트에서 mood/energy를
  뽑는 포트가 계획돼 있음 — 가사·음향 임베딩과 프롬프트 임베딩이 **같은 표현 공간**에 있어야
  유사도 비교가 의미 있음. 임베딩을 그대로 비교할지, 기존처럼 구조화된 mood/energy 값으로
  변환해 비교할지 결정 필요(후자가 기존 hexagonal 아키텍처·해석가능성과 더 잘 맞음).
- **검증 데이터 부재**: 라벨(정답) 없이는 "결합 임베딩이 실제로 더 잘 맞추는지" 확인 불가 —
  최소한 소규모 수작업 평가셋("이 프롬프트엔 이 곡이 맞다" 페어)이 있어야 사전 점검 가능.
  결국 계획된 "감정 라벨링" 라운드와 맞물림.
- **연산 비용**: 전체 카탈로그(660곡) 규모로 확장 시 Whisper+임베딩은 오프라인 사전계산이
  필수(요청 시점 실시간 처리는 무리) — PRD가 이미 백엔드 필요성을 언급한 이유(요청 큐잉 등)와
  같은 선상의 인프라 결정.

> 이 폴더는 정량 결론이 아니라 **다음 라운드(감정 단어 직접 라벨링 → MFCC/CQT 요약통계·발성
> 지표·(실험적으로) 가사/음향 임베딩과 상관·분류)를 위한 밑작업**이다. `research/*` 규칙상
> `main`에 머지하지 않으며, 유의미한 결과가 나오면 보고서 `.md`만 `document-archive`의
> `archive/last-papers/research/`로 별도 반영한다.
