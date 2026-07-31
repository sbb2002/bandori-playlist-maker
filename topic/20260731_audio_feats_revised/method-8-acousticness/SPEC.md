# method-8-acousticness 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §8, "분포 퇴화
> 탈출 조건".

## 실행 환경
- **WSL2 필요** — Essentia 사전학습 `mood_acoustic` 분류기(TensorflowPredict2D 등). 지금은
  실행 불가 — 코드만 작성.

## 산출물

`out/acousticness_raw.csv`:
```
idx, band, song, duration_sec,
acoustic_median, acoustic_p10, acoustic_p90, acoustic_std,
n_patches,
error
```
`out/timeseries/<idx>_acoustic.npy`: 패치별 acoustic 확률 시계열.

## `extract_acousticness.py`

```python
# essentia 공식 모델 저장소의 mood_acoustic 모델(.pb) 사용
# TensorflowPredictMusiCNN 임베딩 → mood_acoustic 분류 헤드, 또는 통합 predictor API
# (WSL2에서 essentia 모델 카드로 정확한 입력 SR·전처리 확정)
# 출력: 패치별 acoustic 클래스 확률(0~1) 시계열
```
- `--model-path` CLI 인자(하드코딩 금지, method-5-energy와 동일 원칙).

## 분포 퇴화 점검 (이 스크립트가 아니라 별도 분석에서 수행 — 여기선 훅만)
- `out/acoustic_raw.csv` 산출 후 **별도로** `out/distribution_check.py`(선택, 시간 되면)를
  작성: acoustic_median의 IQR·히스토그램을 찍어 `out/distribution_check.md`에 기록. 이번
  라운드에서 필수는 아님 — 없으면 생략하고 README에 "미구현" 명시.

## 검증 방법 (내가 수행)
- WSL2 구축 전까지 정적 리뷰만: CONVENTIONS 준수 여부, resume/에러격리, timeseries 저장 확인.
