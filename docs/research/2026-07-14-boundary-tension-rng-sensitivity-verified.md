# 2026-07-14 — boundary_tension 회귀가드 민감도, RNG-정렬 가설 검증 결과

## 배경 요약

`docs/reports/2026-07-13-boundary-tension-sensitivity-open-question.md`에서 제기된 미해결
이슈: PR #7에서 중복 업로드 곡 2개(idx 525, 588)를 `data/songs_master.csv`에서 제거했더니
(661→659행, 헤더 포함), `test_boundary_tension_continuity_is_smooth`의 seed=0 고정 시나리오
(`_quiet_params()`, target_seconds=3600)에서 평균 경계 gap이 0.40 미만(통과) → 0.437(실패)로
튀어 임계값을 0.44로 재조정했다. 곡 전체의 0.3%만 빠졌는데 이 정도로 값이 튄 것이 이상해서,
다음 가설이 세워졌다:

> **RNG-정렬 가설**: `build_setlist()` Stage A가 스테이지마다 공유된 단일 `random.Random`
> 인스턴스에 `rng.shuffle(window)`를 호출한다. 곡이 빠지면 스테이지별 `window` 길이가 달라져
> `rng.shuffle`이 소비하는 난수 호출 횟수가 달라지고, 그 결과 이후 모든 스테이지의 RNG 상태가
> 밀릴 수 있다 — 즉 실제 후보 풀 품질 저하가 아니라 RNG 소비량 어긋남(misalignment)에 의한
> 아티팩트일 수 있다는 가설.

## 검증 방법

`data/legacy/songs_master_legacy.csv`(제거 전, 661행)와 `data/songs_master.csv`(제거 후,
659행) 양쪽에 대해 `build_setlist(songs, _quiet_params(), target_seconds=3600,
rng=random.Random(0))`를 재현하는 스크립트를 작성했다(스크래치 파일, 커밋 안 함). `random.Random`을
서브클래싱한 `LoggingRandom`으로 `shuffle()`/`choice()` 호출마다 (a) 전달된 리스트 길이, (b)
셔플 **직전** 리스트의 idx 순서, (c) 셔플 **직후** idx 순서를 기록해, Stage A의 candidate window
크기와 순서, Stage B의 `rng.choice` 호출 횟수를 두 데이터셋 간에 직접 비교했다.

## 스테이지별 비교 데이터

### Stage A `rng.shuffle(window)` 소비량 — 가설의 핵심 예측 대상

| 스테이지 | window 크기 (BEFORE, 661행) | window 크기 (AFTER, 659행) |
|---|---|---|
| 0 | 44 | 44 |
| 1 | 38 | 38 |
| 2 | 32 | 32 |

**세 스테이지 모두 window 크기가 완전히 동일하다.** 즉 `rng.shuffle`이 소비하는 Fisher–Yates
스왑 횟수(및 그에 따른 `random()` 호출 횟수)는 제거 전/후로 **전혀 달라지지 않았다** — idx
525, 588 두 곡 모두 `_quiet_params()`(목표 강도 0.15, 허용창 ±0.08)의 Stage A 허용창 안에
들지 않았기 때문이다. Stage B의 `rng.choice()` 호출 횟수도 양쪽 모두 14회로 동일했다.

이 결과만으로 RNG-정렬 가설의 **핵심 메커니즘(window 길이 변화 → 난수 소비량 어긋남)은 이미
반증**된다: 소비량이 어긋나려면 애초에 소비 횟수 자체가 달라져야 하는데, 그렇지 않았다.

### Stage A window 내용물(순서) — 실제 원인

그런데도 셔플 **직전** window의 idx 리스트 자체는 두 데이터셋에서 순서가 다르다(스테이지 0
예시, 앞부분 발췌):

```
BEFORE: [568, 240, 403, 19, 417, 405, 310, 64, 242, 208, 590, 545, 343, 324, 20, 603, ...]
AFTER:  [568, 240, 403, 19, 417, 405, 64, 310, 242, 590, 208, 545, 343, 324, 20, 603, ...]
                              ^^^^^^^^ 여기부터 정렬 순서가 어긋남
```

두 window는 **곡 집합(멤버십)은 거의 동일**하지만(idx 525/588은 애초에 창 밖이라 집합 차이도
아님) **정렬 순서가 다르다**. Stage A의 정렬 키는 `(abs(s.energy - target), s.idx)`이고
`idx`가 완전한 동점 해소자이므로, 이 순서 차이는 `s.energy` 값 자체가 두 데이터셋에서 미세하게
다르다는 뜻이다. 셔플 직전 리스트 순서가 다르면 **같은 seed로 같은 크기의 Fisher–Yates 셔플을
돌려도 셔플 결과(및 이후 상위 `count`개 선택)가 달라진다** — 이것이 실제로 관측된 선곡 분기의
직접적인 메커니즘이다.

### 왜 `energy`가 두 데이터셋에서 다른가 — 근본 원인

`src/backend/app/repo/song_repo.py`의 `_percentile_ranker()`/`intensity()`를 확인한 결과,
`Song.energy`(강도)는 **곡 하나의 고정된 절대값이 아니라, `eligible` 후보 풀 전체 분포에 대한
백분위 순위(percentile rank)를 여러 신호에 대해 power-mean(p=3)으로 합성한 값**이다:

```python
def _percentile_ranker(values: list[float]) -> Callable[[float], float]:
    srt = sorted(values)
    n = len(srt)
    def rank(v: float) -> float:
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n
    return rank
```

`eligible` 풀에서 곡을 단 2개만 제거해도 `srt`(정렬된 분포)와 `n`이 바뀌므로, **그 2곡과 아무
관련 없는 나머지 656/658곡 각각의 percentile rank(=energy)도 미세하게 재계산된다.** 이 미세한
재계산이 Stage A 정렬 키의 동점 부근에서 순서를 뒤집기에 충분했고, 그 결과 `rng.shuffle`에
들어가는 리스트 순서가 달라져 최종 선곡·시퀀싱이 위치 1(스테이지 0의 두 번째 곡)부터 분기했다
(`legacy: [568, 590, 466, ...]` vs `new: [568, 442, 240, ...]`).

### 선곡 idx 비교 (seed=0, 3 스테이지)

| | BEFORE (661행) | AFTER (659행) |
|---|---|---|
| Stage 0 | 568, 590, 466, 603, 240, 64 | 568, 442, 240, 64, 603, 466 |
| Stage 1 | 403, 189, 90, 442, 88, 416 | 403, 189, 90, 88, 590, 416 |
| Stage 2 | 92, 131, 310, 260, 108 | 360, 131, 310, 260, 108 |
| 평균 경계 gap | 0.349 | 0.437 |

제거된 idx 525/588은 BEFORE 선곡 목록에도 등장하지 않는다(둘 다 애초에 이 시나리오에서
선택되지 않던 곡). 즉 "빠진 곡이 원래 매끄러운 다리 역할을 하던 곡이었다"는 원 보고서의 가설
①(우연)도 성립하지 않는다 — 그 곡들은 애초에 선곡 후보에 오르지도 않았다.

## 결론: 가설 REFUTED (부분적)

**"RNG 소비량이 스테이지 간 어긋난다"는 원래의 RNG-정렬 가설은 반증(REFUTED)된다** — Stage A
window 크기(및 Stage B choice 호출 횟수)는 제거 전/후로 완전히 동일했으므로, RNG가 소비하는
호출 횟수 자체는 어긋나지 않았다.

그러나 **더 넓은 의미의 "RNG 기반 셔플이 사소한 풀 변화에 과민하다"는 직관은 유효하며**, 실제
메커니즘이 다음과 같이 규명되었다:

> `Song.energy`가 **전체 후보 풀에 대한 상대적 percentile rank**로 계산되기 때문에, 풀에서
> **단 2곡만 제거해도 나머지 모든 곡의 energy 값이 미세하게 재계산**되고, 이 미세한 변화이
> Stage A의 `(abs(energy-target), idx)` 정렬 키의 동점 근방에서 순서를 뒤집는다. `rng.shuffle`은
> 입력 리스트의 초기 순서에 따라 다른 순열을 만들어내므로, 순서가 뒤집힌 리스트에 동일 seed로
> 셔플을 적용해도 결과가 달라진다 — 이것이 선곡 분기의 직접 원인이다.

즉 이번 사례는 "후보 풀 품질이 실제로 나빠졌다"(대안 가설 ②의 스카시티 버전)는 것도 아니고,
"RNG 소비 카운트가 밀렸다"(원 가설)는 것도 아니다. **percentile 정규화의 전역적(global)
특성과 RNG 셔플의 초기-순서-의존성이 상호작용해, 관련 없어 보이는 소수의 풀 변경도 전체
선곡 결과를 크게 흔들 수 있다**는, 구조적이지만 원 가설과는 다른 메커니즘이다.

이 구조 자체는 버그는 아니다 — percentile 정규화는 "목표 0.15가 진짜 하위 15% 곡을 가리키게"
하려는 의도적 설계(코드 주석 참고)이고, 데이터가 바뀔 때마다 전역 재계산되는 것은 당연한
결과다. 다만 **회귀가드 테스트가 이런 전역 민감도에 취약한 정확한 실측값(0.437)에 타이트하게
붙어 있다는 점**은 유지보수 관점에서 눈여겨볼 부분이다.

## 회귀가드 임계값 재검증

`python -m pytest`(9개 테스트, `src/` 디렉터리 기준)를 실행한 결과 현재 코드 기준 전부
통과했다:

```
tests/test_integration.py::test_boundary_tension_continuity_is_smooth PASSED
============================== 9 passed in 0.10s ==============================
```

실측 평균 gap은 0.4374(반올림 전)로, 현재 임계값 0.44 대비 여유가 크지 않다(margin ≈ 0.0026).
베이스라인(연속성 로직 미적용, ~0.56) 대비로는 여전히 크게 개선된 수준이라 임계값 0.44 자체는
**당장은 타당**하지만, 위에서 규명한 전역 민감도 구조상 향후 데이터 곡 수가 다시 바뀌면(신곡
추가/제거) 이 값이 또 튈 가능성이 높다.

## 권장 후속 조치 (실제 코드 수정은 별도 `feature/*` 브랜치에서)

이 브랜치는 조사 전용이라 `src/` 코드를 수정하지 않았다. 다음은 제안일 뿐이다:

1. **스테이지별 독립 RNG 시드 분리**: 현재 단일 `rng` 인스턴스를 스테이지 전체에서 공유한다.
   `rng = random.Random((base_seed, stage_index))` 식으로 스테이지마다 파생 시드를 쓰면, 최소한
   "한 스테이지의 변화가 이후 스테이지에 전파"되는 경로는 차단된다(다만 이번 사례처럼 각
   스테이지 *내부*의 정렬 순서 변화까지는 못 막는다 — energy percentile 자체가 전역이므로).
2. **회귀가드를 실측값 하드코딩 대신 상대적 개선폭으로 판정**: 현재 테스트가 "절대 임계값
   0.44"에 의존하는데, 위 구조상 데이터가 바뀔 때마다 실측값이 흔들릴 수 있다. 예:
   "연속성 로직 적용 후 평균 gap이 베이스라인(연속성 미적용) 대비 X% 이상 개선"처럼 상대
   지표로 바꾸면 데이터 변경에 덜 취약해질 수 있다.
3. **`energy` percentile 재계산의 민감도 자체를 완화**: 예컨대 percentile rank를 고정된
   레퍼런스 분포(스냅샷) 기준으로 계산하고 신곡 추가 시에만 주기적으로 재보정하는 방식이면,
   곡 1~2개 증감이 전체 order를 흔드는 정도를 줄일 수 있다. 다만 이는 PRD 오픈 이슈(재추출
   필요성)와 맞물려 있어 신중한 설계가 필요.
4. 위 조치들은 파일럿 튜닝 우선순위(`docs/research/2026-07-11-playlist-sequencing-strategy.md`
   §8)와 함께 재검토할 것을 권장.

## 참고

- 원 오픈 이슈: `docs/reports/2026-07-13-boundary-tension-sensitivity-open-question.md`
- PR #7: https://github.com/sbb2002/bandori-playlist-maker/pull/7
- 관련 코드: `src/backend/app/domain/selection.py`(`build_setlist`, Stage A/B),
  `src/backend/app/repo/song_repo.py`(`_percentile_ranker`, `intensity`),
  `src/tests/test_integration.py`(`test_boundary_tension_continuity_is_smooth`)
- 검증 데이터: `data/songs_master.csv`(659행) vs `data/legacy/songs_master_legacy.csv`(661행)
