# method-4-loudness 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §4.

## 실행 환경
- **네이티브(Windows Python 가능)** — `pyloudnorm`만 사용(이미 설치돼 있음: 0.2.0). 전량
  즉시 실행 가능.

## 산출물

`out/loudness_raw.csv`:
```
idx, band, song, duration_sec,
lufs_integrated,           # 통합 라우드니스(대표값), pyloudnorm Meter.integrated_loudness
lra,                       # EBU R128 Loudness Range ≈ p95-p10 of short-term loudness
st_median, st_p10, st_p90, st_std,  # short-term(3s) loudness 요약통계(공통 규약 준용 참고용)
mastering_flag,            # 아래 "정규화 혼입 점검" 결과
error
```

## `extract_loudness.py`

```python
import pyloudnorm as pyln
import soundfile as sf
import numpy as np

def short_term_loudness(data: np.ndarray, rate: int, window_sec: float = 3.0) -> np.ndarray:
    # pyln.Meter(rate)로 3초 윈도우(50% 겹침 등 EBU R128 관례)마다 integrated_loudness 계산
    # 무음/무효 구간(-70LUFS 이하 절대게이팅)은 제외하고 배열 반환

def extract_features(path: Path) -> dict:
    # data, rate = sf.read(str(path))  # librosa 대신 soundfile 직접 사용(정밀도)
    # meter = pyln.Meter(rate)
    # lufs_integrated = meter.integrated_loudness(data)
    # st = short_term_loudness(data, rate)
    # lra = np.percentile(st, 95) - np.percentile(st, 10)
    # st_median/p10/p90/std = 각각 계산
    # mastering_flag: lufs_integrated가 흔한 스트리밍 타깃(-14, -16, -23 LUFS 등) 근처(±0.3)에
    #   비정상적으로 몰려있는 곡 표시(파이프라인 뒤 EDA에서 일괄 비교하되, 여기선 원시값만 저장
    #   해도 됨 — mastering_flag는 optional, 시간 부족하면 생략 가능)
    ...
```

## 검증 방법 (내가 수행)
- `--limit 5`로 즉시 실행, LUFS 값이 상식 범위(-30~-5 정도)인지, LRA가 0 이상인지 확인.
- `--idx`로 이미 알려진 대비 곡(조용한 곡 vs 시끄러운 곡, `songs_master.csv`의 shape 컬럼
  참고) 몇 개 비교해 방향성 타당한지 점검.
