# 모드 스케일 확장 key 검증 (30곡, K-S major/minor 2모드 -> 7개 교회선법)

## 방법론 한계 (필독)

Krumhansl-Kessler major/minor 프로파일은 실증 청취실험 기반이지만, 나머지 5개
모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)는 그런 실증 데이터가 없다.
여기서는 major/minor 프로파일에서 각 모드의 특징음 가중치를 맞바꾸는 방식의
**휴리스틱 근사 템플릿**을 썼다 — 통계적으로 검증된 값이 아니므로 참고용으로만
해석할 것.

## 표본: 50곡 (bass_key_validation과 동일, seed=42)

- 장/단조가 아닌 모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)로 판정된 곡: 21/50 (42.0%)
- 모드 판정의 장/단조 계열(family)이 기존 K-S mode_ks와 일치: 94.0%

## roselia 표본

| idx | song | K-S | Essentia | Modal(7선법) | non-major/minor |
|---|---|---|---|---|---|
| 575 | Re:birth day | D/major | G/major | D/mixolydian | True |
| 605 | 名前のない怪物 | F/major | F/major | F/ionian | False |
| 606 | Dazzle the Destiny | A/major | F#/minor | A/lydian | True |
| 618 | Talk to My Tone | C/major | C/major | C/ionian | False |
| 656 | Preserved Roses (Cover) | F#/major | F#/major | F#/dorian | True |
| 631 | Proud of oneself | E/minor | A/minor | E/phrygian | True |

## 전체 30곡 상세

| idx | band | K-S | Essentia | Modal | conf |
|---|---|---|---|---|---|
| 6 | afterglow | D/major | D/major | D/ionian | 0.535 |
| 25 | afterglow | A/major | A/major | A/ionian | 0.493 |
| 27 | afterglow | A/minor | A/minor | A/aeolian | 0.518 |
| 30 | afterglow | A/major | A/minor | A/mixolydian | 0.269 |
| 32 | afterglow | G#/major | Ab/minor | G#/ionian | 0.349 |
| 89 | ave_mujica | G#/minor | E/major | G#/phrygian | 0.293 |
| 95 | ave_mujica | B/minor | B/minor | B/aeolian | 0.623 |
| 104 | various_artists | G#/major | Ab/major | G#/ionian | 0.509 |
| 114 | hello_happy_world | D/major | A/major | D/ionian | 0.349 |
| 142 | hello_happy_world | C/major | F/major | F/ionian | 0.379 |
| 163 | hello_happy_world | G#/major | Ab/major | G#/mixolydian | 0.310 |
| 203 | morfonica | E/major | E/major | E/ionian | 0.682 |
| 223 | morfonica | A/minor | A/minor | A/phrygian | 0.240 |
| 225 | morfonica | A#/minor | B/major | A#/phrygian | 0.436 |
| 228 | morfonica | A/minor | A/minor | A/phrygian | 0.598 |
| 238 | mugendai_mutype | E/minor | A/minor | E/phrygian | 0.351 |
| 250 | mugendai_mutype | C#/minor | F#/minor | C#/locrian | 0.297 |
| 281 | mygo | A#/major | Bb/major | A#/ionian | 0.712 |
| 284 | mygo | C#/minor | A/major | C#/phrygian | 0.473 |
| 348 | pastel_palettes | D#/major | Eb/major | D#/ionian | 0.599 |
| 429 | poppin_party | E/minor | G/major | E/dorian | 0.251 |
| 432 | poppin_party | F/major | F/major | F/ionian | 0.690 |
| 459 | poppin_party | G/minor | Eb/major | G/aeolian | 0.173 |
| 517 | raise_a_suilen | G#/major | Ab/major | G#/ionian | 0.396 |
| 559 | raise_a_suilen | F#/minor | C#/minor | F#/locrian | 0.194 |
| 575 | roselia | D/major | G/major | D/mixolydian | 0.315 |
| 605 | roselia | F/major | F/major | F/ionian | 0.277 |
| 606 | roselia | A/major | F#/minor | A/lydian | 0.221 |
| 618 | roselia | C/major | C/major | C/ionian | 0.656 |
| 656 | roselia | F#/major | F#/major | F#/dorian | 0.254 |
| 13 | afterglow | C#/major | F#/minor | C#/ionian | 0.324 |
| 29 | afterglow | B/minor | D/major | D/ionian | 0.319 |
| 149 | hello_happy_world | G/major | G/major | G/ionian | 0.434 |
| 176 | hello_happy_world | F#/major | F#/major | F#/ionian | 0.306 |
| 181 | morfonica | G/minor | F/minor | G/dorian | 0.358 |
| 182 | morfonica | A/minor | A/minor | A/aeolian | 0.608 |
| 254 | mugendai_mutype | A/major | D/major | A/ionian | 0.234 |
| 263 | mygo | A#/minor | Bb/minor | A#/aeolian | 0.364 |
| 282 | mygo | C#/major | Ab/minor | C#/ionian | 0.177 |
| 303 | pastel_palettes | G/major | C/major | B/phrygian | 0.309 |
| 306 | pastel_palettes | E/major | E/major | E/ionian | 0.210 |
| 328 | pastel_palettes | E/minor | G/major | E/dorian | 0.240 |
| 375 | poppin_party | B/major | B/major | B/ionian | 0.319 |
| 384 | poppin_party | B/minor | E/minor | B/phrygian | 0.804 |
| 419 | poppin_party | D/major | E/minor | D/ionian | 0.464 |
| 422 | poppin_party | B/major | B/major | B/ionian | 0.461 |
| 492 | raise_a_suilen | F#/minor | B/minor | F#/phrygian | 0.666 |
| 544 | raise_a_suilen | B/major | B/major | B/ionian | 0.486 |
| 553 | raise_a_suilen | F/minor | F/minor | F/dorian | 0.357 |
| 631 | roselia | E/minor | A/minor | E/phrygian | 0.390 |