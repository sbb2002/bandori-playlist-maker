# 모드 스케일 확장 key 검증 (736곡 전체, K-S major/minor 2모드 -> 7개 교회선법)

## 방법론 한계 (필독)

Krumhansl-Kessler major/minor 프로파일은 실증 청취실험 기반이지만, 나머지 5개
모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)는 그런 실증 데이터가 없다.
여기서는 major/minor 프로파일에서 각 모드의 특징음 가중치를 맞바꾸는 방식의
**휴리스틱 근사 템플릿**을 썼다 — 통계적으로 검증된 값이 아니므로 참고용으로만
해석할 것.

## 표본: 736곡 (songs_master.csv 전체, 50곡 파일럿의 확장판)

- 장/단조가 아닌 모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)로 판정된 곡: 343/736 (46.6%)
- 모드 판정의 장/단조 계열(family)이 기존 K-S mode_ks와 일치: 87.6%
- 실패(오디오 없음/에러): 0곡

## 밴드별 non-major/minor 비율

| band | n | non_major_minor | 비율 |
|---|---|---|---|
| millsage | 2 | 2 | 100.0% |
| ikka_dumb_rock | 1 | 1 | 100.0% |
| morfonica | 58 | 39 | 67.2% |
| mygo | 60 | 32 | 53.3% |
| roselia | 91 | 48 | 52.7% |
| mugendai_mutype | 77 | 39 | 50.6% |
| hello_happy_world | 72 | 33 | 45.8% |
| ave_mujica | 29 | 13 | 44.8% |
| raise_a_suilen | 79 | 35 | 44.3% |
| pastel_palettes | 74 | 31 | 41.9% |
| poppin_party | 116 | 48 | 41.4% |
| afterglow | 72 | 21 | 29.2% |
| various_artists | 5 | 1 | 20.0% |

## roselia 전체 (91곡) mode_modal 분포

| mode_modal | 곡수 | 비율 |
|---|---|---|
| aeolian | 23 | 25.3% |
| phrygian | 21 | 23.1% |
| ionian | 20 | 22.0% |
| dorian | 11 | 12.1% |
| mixolydian | 8 | 8.8% |
| lydian | 4 | 4.4% |
| locrian | 4 | 4.4% |

- Phrygian 비율: 23.1% (21/91)

## morfonica 전체 (58곡) mode_modal 분포

| mode_modal | 곡수 | 비율 |
|---|---|---|
| phrygian | 21 | 36.2% |
| ionian | 13 | 22.4% |
| dorian | 7 | 12.1% |
| aeolian | 6 | 10.3% |
| locrian | 6 | 10.3% |
| lydian | 3 | 5.2% |
| mixolydian | 2 | 3.4% |

- K-S에서 minor로 분류된 36곡 중 실제로는 Phrygian으로 재분류된 비율: 52.8% (19/36)