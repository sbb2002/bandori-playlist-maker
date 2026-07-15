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

- `fig/mfcc/<band>_mfcc.png` (10장) — 밴드당 1장, **2×3 레이아웃**: 위=raw mix MFCC, 아래=
  vocal-only MFCC, 가로=밴드의 3곡. 위아래 패딩을 없애(hspace=0) raw↔vocal을 세로로 직접 대비.
  **0번 계수(로그 에너지)는 스케일을 지배해 제외**하고 계수 1–19만 표시, 색범위는 밴드 내
  raw+vocal 공유 + 98퍼센타일 robust(대비 확보). CJK 폰트(Yu Gothic)로 일본어 제목 렌더링.
- `combined_metrics.csv` (30행) — 곡별 지표 통합(`extract_metrics.py`):
  - **기존 지표**(앱이 쓰는 것, `data/song_features_with_proxies.csv`에서): mode_score·energy_proxy·
    acousticness_proxy·instrumentalness_proxy·harmonic_ratio·voiced_frac_mix·tempo_excerpt·key.
  - **연구 지표**(mood-warmth 보컬 발성 계열, vocal 스템에서 재계산): jitter_local·shimmer_local·
    hnr_mean·f0_median_st·f0_range_st·f0_std_st·vocal_ratio·vocal_centroid.
- `fig/metrics/<metric>.png` — 지표별 밴드색 가로 막대(30곡, `plot_metrics.py`). 밴드 경향이
  갈라지는지 정성 스캔용.

## 재생성 순서

```
cd research/mfcc_analysis   # 오디오 스택 env(librosa/parselmouth/demucs/matplotlib)
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

> 이 폴더는 정량 결론이 아니라 **다음 라운드(감정 단어 직접 라벨링 → MFCC 요약통계/발성 지표와
> 상관·분류)를 위한 밑작업**이다. `research/*` 규칙상 `main`에 머지하지 않으며, 유의미한 결과가
> 나오면 보고서 `.md`만 `document-archive`의 `archive/research/`로 별도 반영한다.
