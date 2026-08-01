# Bass-Key Validation Report (50곡, GPU demucs 재확장)

## 방법론

1. 전체믹스: K-S 템플릿 매칭(24템플릿, major/minor)
2. 베이스 스템: demucs(--two-stems bass, htdemucs, GPU)로 분리 후 동일 K-S 알고리즘 적용
3. seed=42 기준 30곡 + 결정론적 추가 20곡(roselia+1, morfonica+2 포함) = 50곡

## 결과

| 비교 | 일치 | 비율 |
|---|---|---|
| 베이스 vs 전체믹스 K-S (정확한 key) | 24/50 | 48.0% |
| 베이스 vs Essentia (정확한 key) | 21/50 | 42.0% |
| 베이스 vs K-S (mode만) | | 72.0% |
| 베이스 vs Essentia (mode만) | | 74.0% |
| morfonica+roselia(12곡) 중 K-S 일치 | 5/12 | 41.7% |

## 30곡 -> 50곡 비교

| 지표 | 30곡 | 50곡 |
|---|---|---|
| 베이스 vs K-S | 43.3% | 48.0% |
| 베이스 vs Essentia | 33.3% | 42.0% |

표본을 늘려도 결론은 바뀌지 않음 — 여전히 베이스 단독으로는 key 검증에 부족.

## morfonica/roselia 상세

| idx | band | song | K-S | Bass | 일치 |
|---|---|---|---|---|---|
| 203 | morfonica | One step at a time | E/major | E/major | True |
| 223 | morfonica | 祝福 (Cover) | A/minor | D/minor | False |
| 225 | morfonica | かくれんぼ (Cover) | A#/minor | A#/minor | True |
| 228 | morfonica | Nameless Story (Cover) | A/minor | C/major | False |
| 575 | roselia | Re:birth day | D/major | C/major | False |
| 605 | roselia | 名前のない怪物 | F/major | D/minor | False |
| 606 | roselia | Dazzle the Destiny | A/major | A/major | True |
| 618 | roselia | Talk to My Tone | C/major | C/major | True |
| 656 | roselia | Preserved Roses (Cover) | F#/major | A/major | False |
| 181 | morfonica | メランコリックララバイ | G/minor | F/minor | False |
| 182 | morfonica | flame of hope | A/minor | A/minor | True |
| 631 | roselia | Proud of oneself | E/minor | A/minor | False |

## 결론

50곡으로 늘려도 베이스 vs 전체믹스 K-S 일치율은 40%대 초반에 머물러, 베이스 스템이
key 검증 수단으로 부적합하다는 30곡 때 결론이 그대로 재확인됐다. mode(장/단조)만
놓고 보면 70%대로 훨씬 안정적이라는 점도 동일하다.

**생성**: 2026-08-01T13:35:20.339058
**표본**: 50곡 (seed=42 30곡 + 결정론적 추가 20곡, GPU demucs로 재확장)