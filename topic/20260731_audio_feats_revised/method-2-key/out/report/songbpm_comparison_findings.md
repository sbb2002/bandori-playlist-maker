# songbpm.com 대조를 통한 조성(key) 추정 정확도 분석

## 1. 방법론

- Bestdori에는 공식 key 데이터가 없어, 비공식이지만 Spotify 오디오 분석 데이터를 노출하는
  `songbpm.com`을 레퍼런스로 사용했다.
- 표본 10곡 이상인 9개 밴드(afterglow, roselia, morfonica, poppin_party, mygo,
  raise_a_suilen, pastel_palettes, mugendai_mutype, hello_happy_world, ave_mujica) 중
  8개 밴드에서 songbpm.com에 존재하는 곡을 `WebSearch`(`site:songbpm.com <band>`) +
  아티스트 목록 페이지(`songbpm.com/@<band>`)로 탐색하고, 각 곡 페이지를 `WebFetch`로 열어
  "The track runs ... with a X key and a Y mode." 문장을 파싱했다.
- **mugendai_mutype**는 songbpm.com에서 전혀 검색되지 않아(2차 창작 프로젝트로 Spotify에
  없음) 표본에서 제외됐다.
- 매칭 시 "(Cover)" 표기, instrumental 버전(가급적 보컬 버전 우선 선택), 곡 길이(duration_sec)
  대조를 통해 정합성을 확인했고, 제목이 부분적으로만 비슷하거나 key/mode 정보가
  placeholder(미기재)인 페이지는 제외했다. 향/반각, 공백 차이는 정규화해서 비교했다.
- 목표 표본 크기는 원래 60곡이었으나, 코디네이터 지시로 30곡 수준(밴드당 상위 검색 결과
  중심)으로 축소됐다. 실제로는 검색 상위 결과에서 확인 가능한 곡이 예상보다 많아 **44곡**이
  최종 매칭됐다(전수 탐색은 하지 않음).
- key 비교 시 `Ab=G#`, `Bb=A#`, `Db=C#`, `Eb=D#`, `Gb=F#` 등 이명동음 표기는 동일 key로 정규화했다.

## 2. 표본 크기

**총 44곡**, 8개 밴드(afterglow 4, roselia 5, morfonica 3, poppin_party 1, raise_a_suilen 6,
ave_mujica 6, mygo 9, pastel_palettes 4, hello_happy_world 6). mugendai_mutype는 0곡
(songbpm.com에 데이터 없음).

## 3. 정확도 — K-S 템플릿 매칭 기준

| 지표 | 정확도 |
|---|---|
| key만 정확히 일치 | 52.3% (23/44) |
| mode만 일치 | 77.3% (34/44) |
| key+mode 완전 일치 | 47.7% (21/44) |

## 4. 정확도 — Essentia 기준

| 지표 | 정확도 |
|---|---|
| key만 정확히 일치 | 63.6% (28/44) |
| mode만 일치 | 77.3% (34/44) |
| key+mode 완전 일치 | 59.1% (26/44) |

**Essentia가 K-S보다 key 정확도(+11.3%p)와 완전 일치율(+11.4%p)에서 모두 앞섰다.**
mode-only 정확도는 두 방법이 정확히 동일(77.3%)했다 — 장/단조 판별력 자체는 두 알고리즘이
비슷하고, 차이는 정확한 근음(tonic) 추정 능력에서 갈렸다.

## 5. 밴드별 정확도 (key+mode 완전 일치 기준)

| 밴드 | n | K-S both | Essentia both |
|---|---|---|---|
| afterglow | 4 | 50% | 50% |
| roselia | 5 | 20% | 40% |
| morfonica | 3 | 33% | 0% |
| poppin_party | 1 | 100% | 100% |
| raise_a_suilen | 6 | 50% | 67% |
| ave_mujica | 6 | 50% | 67% |
| mygo | 9 | 44% | 67% |
| pastel_palettes | 4 | 25% | 50% |
| hello_happy_world | 6 | 83% | 83% |

hello_happy_world와 poppin_party(표본 1곡뿐)를 빼면 대체로 50~70%대에 머무르고,
roselia·morfonica·pastel_palettes는 K-S 기준으로 특히 낮다(20~33%). morfonica는 표본이
3곡뿐이라 신뢰구간이 넓다(Essentia 0/3은 우연히 다 틀린 경우일 수 있음).
mygo·raise_a_suilen·ave_mujica·pastel_palettes 4개 밴드 모두 Essentia가 K-S보다
both-match에서 뚜렷이 높았다(+17~+25%p) — 특히 mygo(9곡, 최대 표본)에서 Essentia 67% vs
K-S 44%로 격차가 컸다.

## 6. 근접조 혼동 패턴

key가 불일치한 곡들을 반음 거리로 분류했다(같은 mode인데 완전4·5도=5반음 이웃,
mode가 다르면서 단3도=3반음 차이인 "관계조(relative major/minor)" 혼동, 그 외 기타).

| 방법 | key 불일치 곡수 | 완전4·5도 이웃 | 관계조(장단조 바뀜) | 기타 |
|---|---|---|---|---|
| K-S | 21 | 12 (57%) | 3 (14%) | 6 (29%) |
| Essentia | 16 | 8 (50%) | 5 (31%) | 3 (19%) |

**즉 K-S key 오류의 71%(12+3/21), Essentia key 오류의 81%(8+5/16)가 완전4·5도 이웃
또는 관계조 혼동이라는 "음악이론적으로 근접한" 오류였다** — 무작위 오류가 아니라
으뜸음 후보(딸림음/버금딸림음, 나란한조)로 흔히 혼동되는 자리로 수렴하는 경향이
뚜렷했다. Essentia는 관계조 혼동 비율이 K-S보다 두 배 이상 높아(31% vs 14%),
Essentia의 남은 오류는 주로 "장/단조 라벨은 틀렸지만 근음 자체는 음악적으로
타당한 이웃"인 경우가 많음을 시사한다.

배경에서 제시된 4개 수동 대조 사례도 이 패턴과 일치한다: flame of hope(완전5도
이웃, mode 일치), Re:birth Day(완전4도 이웃, mode 일치, Essentia가 정확히 맞춤),
Daylight(mode 자체 불일치), ALIVE(K-S가 정확·Essentia는 완전히 이탈 — B major는
근접조 범주에 들지 않는 큰 오류).

## 7. 결론

1. **Essentia가 K-S 템플릿 매칭보다 전반적으로 더 정확하다.** key-only, both-match
   모두에서 10%p 이상 앞섰고, mode-only는 동률이다. 이는 배경에서 언급된 4곡 수동
   대조(K-S 3승 1패 우세로 보였던 것)와 다른 결론이며, 표본을 늘리자 오히려
   Essentia 우위가 드러났다.
2. **mode(장/단조) 판별은 key(정확한 으뜸음) 판별보다 훨씬 신뢰도가 높다** — 두
   방법 모두 mode-only 정확도가 77.3%로 key-only(52~64%)보다 확연히 높다. 조성
   기반 후속 분석(예: valence 프록시)을 설계한다면 정확한 key보다 major/minor
   이분법에 의존하는 편이 안전하다.
3. **key 오류의 대다수(70~80%)는 음악이론적으로 설명 가능한 근접조 혼동**(완전
   4·5도 이웃, 관계조)이다. 완전 무작위 오류가 아니므로, "key가 정확히 일치하지
   않아도 완전4·5도 이내"를 허용 오차로 삼는 완화된 정확도 지표를 병행 보고하는
   것이 실무적으로 더 의미 있을 수 있다(참고: "key 완전4·5도 이내 + mode 일치"로
   완화하면 K-S both-match는 47.7%→72.7%, Essentia는 59.1%→75.0%로 상승한다).
4. **밴드별 편차가 크다** — hello_happy_world(83%)처럼 매우 높은 밴드가 있는 반면
   roselia(K-S 20%)처럼 낮은 밴드도 있어, 단일 정확도 수치로 전체 파이프라인의
   신뢰도를 일반화하기보다 밴드/장르별 특성(악기 편성, 코드 보이싱의 복잡도 등)을
   고려한 해석이 필요하다.
5. 표본이 44곡(전체 736곡 중 약 6%)에 그치고 songbpm.com 자체도 비공식·자동 추정
   데이터라는 한계가 있어, 이 결과는 "정답"이 아니라 "두 자동 추정 방법 간의
   상대적 신뢰도 비교"로 해석해야 한다.
