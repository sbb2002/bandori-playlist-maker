# method-9-instrumentalness 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §9, "분포 퇴화
> 탈출 조건".

## 실행 환경
- **WSL2 필요** — `extract_instrumentalness_essentia.py`: Essentia `voice_instrumental`
  분류기. 지금은 실행 불가 — 코드만 작성.
- **네이티브(Windows Python 가능)** — `extract_instrumentalness_stem.py`: 보유 보컬 스템의
  에너지비 계산은 librosa/soundfile만으로 가능 — **즉시 실행 가능**.

## ⚠️ 스템 가용성 (CONVENTIONS.md 참조)
- `VOCAL_STEM_DIR`에는 661곡 중 **30곡분만** 존재(`{band}__{idx:03d}/vocals.wav`,
  `no_vocals.wav`). 나머지 idx는 `error="no_stem"`으로 기록하고 건너뛴다(스크립트가 죽지
  않아야 함) — 이번 라운드는 이 30곡 파일럿 표본으로 검증하는 것이 목표.

## 산출물

`out/instrumentalness_raw.csv`:
```
idx, band, song, duration_sec,
instr_stem_ratio,          # 1 - vocal_energy/total_energy (스템 있는 30곡만)
voice_median, voice_p10, voice_p90, voice_std,  # Essentia 분류기 확률(1-voice=instrumental 관점)
n_patches,
error                       # "no_stem" 등
```
`out/timeseries/<idx>_voice.npy`: Essentia 분류기 패치별 확률 시계열(WSL2 스크립트가 채움).

## `extract_instrumentalness_stem.py` (네이티브, 1차 구현 대상)

```python
def stem_paths(band: str, idx: int) -> tuple[Path, Path] | None:
    d = VOCAL_STEM_DIR / f"{band}__{idx:03d}"
    if not d.is_dir():
        return None
    return d / "vocals.wav", d / "no_vocals.wav"

def extract_features(band: str, idx: int) -> dict:
    paths = stem_paths(band, idx)
    if paths is None:
        return {"error": "no_stem"}
    vocal_path, instr_path = paths
    # y_vocal, sr = librosa.load(vocal_path, sr=22050, mono=True)
    # y_instr, _  = librosa.load(instr_path, sr=22050, mono=True)
    # vocal_energy = np.sum(y_vocal ** 2)
    # instr_energy = np.sum(y_instr ** 2)
    # total = vocal_energy + instr_energy
    # instr_stem_ratio = instr_energy / total  (= 1 - vocal_energy/total, 정의대로)
    ...
```
- 곡 순회는 `songs_master.csv` 전체를 돌되, `stem_paths`가 `None`이면 스킵(진행 로그에
  "no_stem 스킵" 카운트 별도 표시) — CONVENTIONS의 `_build_tasks` 패턴을
  `path.exists()` 대신 `stem_paths(...) is not None`으로 바꿔 재사용.

## `extract_instrumentalness_essentia.py` (WSL2)
- method-8-acousticness의 `extract_acousticness.py`와 대칭 구조(모델만 `voice_instrumental`
  로 교체). 이미 `out/instrumentalness_raw.csv`가 있으면 idx 기준 컬럼만 병합.

## 검증 방법 (내가 수행)
- `extract_instrumentalness_stem.py`는 30곡 파일럿 표본 전체로 즉시 실행 가능
  (`--idx` 없이 실행하면 자동으로 스템 있는 30곡만 처리되고 나머지는 no_stem으로 스킵).
  값이 0~1 범위인지, 보컬곡 다수인 이 카탈로그 특성상 instr_stem_ratio가 대체로 낮게(보컬
  에너지 비중 높게) 나오는지 확인.
- essentia 버전은 WSL2 구축 전까지 정적 리뷰만.
