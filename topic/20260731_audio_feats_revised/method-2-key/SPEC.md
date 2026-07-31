# method-2-key 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §2.

## 실행 환경
- **네이티브(Windows Python 가능)** — `extract_key_ks.py`: librosa CQT/크로마 + 자체 K-S
  템플릿 매칭만 사용. numpy만 있으면 됨.
- **WSL2 필요** — `extract_key_essentia.py`: Essentia `KeyExtractor` 교차검증. 지금은 실행
  불가(코드만 작성, import 실패 시 안내 메시지 후 종료).

## 산출물

`out/key_raw.csv`:
```
idx, band, song, duration_sec,
key_ks, mode_ks,                         # K-S 다수결 최종(예: "C", "major")
key_ks_confidence,                       # 채택된 키의 지속시간 비율(0~1)
modulation_flag,                         # 2위 후보 지속시간 비율이 임계(예 0.25) 이상이면 True
key_essentia, mode_essentia,             # Essentia 교차검증(WSL2 스크립트가 채움)
key_mismatch, mode_only_mismatch,        # K-S vs Essentia 비교 플래그(WSL2 스크립트가 채움)
error
```
`out/timeseries/<idx>_key_windows.csv`: `window_start_sec, window_end_sec, key, mode, corr` —
윈도우별 매칭 결과 원시 저장(재집계용).

## Krumhansl-Kessler 템플릿 (24개, 하드코딩)

```python
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
# 각 12개 회전 → 24개 템플릿(장조 12키 + 단조 12키)
```

## `extract_key_ks.py`

```python
def sliding_window_keys(path: Path, window_sec: float = 15.0) -> list[dict]:
    # y, sr = librosa.load(path, sr=22050, mono=True)
    # chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)  # (12, frames)
    # frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=512)
    # window_sec 단위로 chroma 프레임을 그룹핑 → 윈도우 평균 크로마 벡터
    # 각 윈도우 벡터를 24개 템플릿과 피어슨 상관 → 최고 상관의 (key, mode, corr)
    # 반환: [{"window_start_sec":.., "window_end_sec":.., "key":.., "mode":.., "corr":..}, ...]

def majority_vote(windows: list[dict]) -> dict:
    # 키별 누적 지속시간(window_end - window_start) 합산 → 최댓값이 대표 key/mode
    # key_ks_confidence = 1위 누적시간 / 전체시간
    # modulation_flag = 2위 누적시간 / 전체시간 >= 0.25

def extract_features(path: Path) -> dict:
    # sliding_window_keys → majority_vote → 결과 dict + duration_sec
    # 윈도우 원시 결과는 out/timeseries/<idx>_key_windows.csv로 별도 저장(호출부에서)
```
- `window_sec` 기본 15초(10~20초 범위 내 파일럿 확정 전까지 임시값), CLI `--window-sec`로
  조정 가능하게.

## `extract_key_essentia.py` (WSL2)

```python
# import essentia.standard as es
# key, scale, strength = es.KeyExtractor()(audio)
# key_essentia = key, mode_essentia = scale ("major"/"minor")
# key_mismatch = (key_ks != key_essentia)
# mode_only_mismatch = (key_ks == key_essentia) and (mode_ks != mode_essentia) — 주의: 실제로는
#   "근접조 판정"이 필요(예: C장조 vs A단조는 관계조라 key_ks==key_essentia 비교로는 못 잡음).
#   상세 판정 로직은 key-profile-bug 관련 기존 산출물(다른 프로젝트)을 참고하되 코드 재사용은
#   하지 말고 이 CSV의 key_ks/key_essentia 두 값만으로 여기서 새로 판정한다.
```
- 이미 `out/key_raw.csv`가 있으면 idx 기준으로 essentia 컬럼만 채워 넣는다(merge, 덮어쓰기 아님).

## 검증 방법 (내가 수행)
- `extract_key_ks.py`는 `--limit 5`로 즉시 실행 가능 — 결과 키가 상식적으로 타당한지
  (동일 밴드 여러 곡 비교 등) 육안 점검.
- `extract_key_essentia.py`는 WSL2 구축 전까지 정적 리뷰만.
