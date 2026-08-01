# method-10-liveness Analysis Report

## Background (Verified Findings)

- **crowd_median distribution degradation**: All 634 valid songs clustered in range 0.000427~0.001721.
  Coefficient of Variation = 0.2041 (far below 0.5 = healthy distribution) → **distribution severely skewed toward low values confirmed**.

- **rt60_est_sec completely clipped**: All 736 songs fixed at exactly 5.0 seconds.
  **This metric is effectively meaningless and provides zero discriminative power.**

- **PANNs success/failure**: 634 successful, 102 failed (crowd_median NaN).

---

## Key Findings

### 1. Top 15 Songs by crowd_median (Sorted Descending)

| Rank | crowd_median | Notes |
|------|--------------|-------|
| 1 | 0.0017213 | Potential false positive (highest) |
| 2 | 0.0015648 | |
| 3 | 0.0015466 | |
| 4 | 0.0015054 | |
| 5 | 0.0014962 | |
| 6 | 0.0014634 | |
| 7 | 0.0014155 | |
| 8 | 0.0013810 | |
| 9 | 0.0013349 | |
| 10 | 0.0012819 | |
| 11 | 0.0012819 | (tied) |
| 12 | 0.0012737 | |
| 13 | 0.0012682 | |
| 14 | 0.0012629 | |
| 15 | 0.0012602 | |

**False positive risk assessment**:
- Per SPEC.md warning: vocal shouts/crowd chants within songs can be misclassified as Crowd/Applause.
- Top songs likely NOT from live recordings (catalog is studio-dominated).
- **Listening verification required** to distinguish real applause from falsely detected effects.

### 2. rt60_est_sec = Completely Useless

- All 736 songs fixed at exactly 5.0 seconds.
- Indicates the estimation algorithm either:
  - Failed to capture reverberation decay in these audio signals, OR
  - Was configured with fixed output range (hard-capped at 5.0s).
- **Cannot differentiate venue acoustics or performance type.**

### 3. Overall Utility Assessment — Critical Evaluation

**Fundamental problem**: This catalog (BanG Dream! songs, studio originals + covers) contains **virtually no live signal**.
- Live concert recordings: <~100 songs estimated
- Studio originals + covers: ~600+ songs

**As a result**:
- `crowd_median` distribution reflects only studio-equipment noise + vocal effects → extremely poor live-ness discrimination power.
- `noise_floor_db` varies due to recording studio/equipment differences, not venue acoustics.
- `rt60_est_sec` = completely meaningless (clipped).

**Practical Conclusion**:
This feature set is only meaningful on **live-recording-rich catalogs**. 
On the current studio-dominated catalog, numeric live-ness judgment is unreliable without auxiliary metadata 
(official live vs. studio labels). Recommend re-evaluation once live concert recordings are collected at scale.

---

## Visualization

- `fig/liveness_dist.png`: crowd_median histogram + top 15 barplot (saved)

---

## 종합 결론(2026-08-01, 실제곡 대조 검증): 이 지표는 사실상 무의미 — 폐기 권고

카탈로그에는 연구자가 **의도적으로 심어둔 "진짜 라이브 실황" 이스터에그 2곡**이
존재한다: `raise_a_suilen "That Is How I Roll! (ライブ / アンコール)"`(idx=526)과
`raise_a_suilen "R・I・O・T (ライブ / アンコール)"`(idx=527). 이 두 곡을 정답
케이스로 삼아 crowd_median의 실제 판별력을 검증했다.

### 검증 결과

| idx | 곡명 | crowd_median | 비고 |
|-----|------|--------------|------|
| 526 | That Is How I Roll! (ライブ / アンコール) | 0.001547 | 상위 15곡 중 3위 — 그러나 카탈로그 최댓값(0.001721)과 큰 차이 없음 |
| 527 | R・I・O・T (ライブ / アンコール) | **NaN** | 추출 자체 실패(102곡 결측 중 하나) |

- 상위 15곡(`fig/liveness_dist.png` 및 위 표 참고)을 전부 훑어봐도 **실제 라이브
  녹음으로 확인되는 곡이 하나도 없음**(연구자 직접 확인).
- 가장 확실한 정답 신호(연구자가 직접 심은 라이브 이스터에그)조차 하나는 순위상
  다른 스튜디오곡들과 구별되지 않고, 다른 하나는 아예 값이 없어 **정답 케이스에서도
  지표가 작동하지 않음**이 확인됨.

### 종합 판단

기존 분석에서 지적된 세 가지 결함(①crowd_median 전 구간 0.0004~0.0017의 극단적
저분산·CV=0.204, ②rt60_est_sec 전곡 5.0 고정으로 사실상 죽은 컬럼, ③102곡/14%
결측)에 더해, **실제 정답 케이스 대조 검증에서도 지표가 라이브 여부를 전혀
구분하지 못함**이 확인되었다. 이는 단순히 "분포가 좁다"는 통계적 약점을 넘어,
"의도된 신호조차 못 잡는다"는 **기능적 실패**로 판단된다.

danceability/acousticness/instrumentalness처럼 "이름과 다른 의미로나마 제한적
활용 가치가 있다"는 결론과 달리, liveness는 **필터 용도로도 신뢰할 수 없어
폐기(또는 rt60 로직 전면 재구현 후 재검증)를 권고**한다. 현재 카탈로그가
스튜디오 녹음 위주라는 근본적 한계는 README가 이미 예견한 바이나, rt60 상수화는
분포 퇴화가 아니라 구현 버그로 의심되므로 별도 점검이 필요하다.
