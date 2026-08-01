# Key (method-2, K-S 템플릿 vs Essentia KeyExtractor) — 상세 리포트

> 요약은 상위 `../../REPORT.md` §2 참고. 이 파일은 key 관련 전체 내용(컬럼 설명·
> 기본 통계·Bestdori 확인·morfonica/roselia 심층분석·베이스 스템 검증·모드 스케일
> 확장 실험)을 담는다.

## 컬럼 설명

컬럼 메타데이터는 `metadata.md`(key_raw.csv), `../timeseries/metadata.md`
(윈도우별 원시 데이터) 참고.

## 기본 통계 (736곡, 2026-08-01 idx 재정렬 이후 최신)

| 지표 | 값 |
|---|---|
| mode_ks (K-S) | major 419 / minor 317 |
| mode_essentia | major 437 / minor 299 |
| key_mismatch (정확한 조성 불일치) | 290 / 736 (39.4%) |
| mode_only_mismatch (조성은 같고 장/단조만 다름) | 35 / 736 |
| **mode만(장/단조만) 일치율** | **73.9%** |

- 정확한 조성(key) 불일치율은 39.4%로 여전히 높지만, **장/단조(mode)만 놓고 보면
  73.9%로 훨씬 안정적**이다. 즉 K-S와 Essentia는 "곡이 전반적으로 밝은지 어두운지"는
  꽤 잘 맞추지만, "정확히 어느 음이 으뜸음인지"에서 자주 갈린다 — 근친조(원둘레상
  이웃 조성, 예: A minor ↔ D minor ↔ E minor) 혼동이 주된 원인으로 추정.
- 두 알고리즘 모두 크로마 기반이라 완전히 독립적인 교차검증은 아니라는 점은 감안할 것.

### 밴드별 mode(장/단조) 일치율 (표본 10곡 이상, 낮은 순)

| band | n | mode 일치율 |
|---|---|---|
| raise_a_suilen | 79 | 63.3% |
| roselia | 91 | 67.0% |
| afterglow | 72 | 70.8% |
| mugendai_mutype | 77 | 72.7% |
| mygo | 60 | 73.3% |
| ave_mujica | 29 | 75.9% |
| poppin_party | 116 | 76.7% |
| morfonica | 58 | 77.6% |
| pastel_palettes | 74 | 79.7% |
| hello_happy_world | 72 | 81.9% |

- **roselia·raise_a_suilen은 mode(장/단조) 자체도 하위권** — 근본적으로 불안정한
  케이스. **morfonica는 mode 기준으론 평균 이상(77.6%)** — 뒤에 나오듯 "A minor 쏠림"
  문제는 장/단조를 잘못 짚은 게 아니라 정확히 어느 minor 조성인지를 헷갈린 것.

## ⚠️ Bestdori 공식 자료 대조 — 불가능함을 확인

Bestdori API(`https://bestdori.com/api/songs/{id}.json`)를 직접 조회해 전체 필드를
확인한 결과, 조성(key)에 해당하는 필드가 **아예 없다**(`bgmId, bgmFile, tag, bandId,
achievements, jacketImage, seq, musicTitle, ruby, phonetic, lyricist, composer,
arranger, howToGet, publishedAt, closedAt, difficulty, length, notes, bpm` — bpm은
있지만 key는 없음). 즉 tempo처럼 "공식 정답과 대조한 정확도"는 애초에 계산 불가능하다.
알고리즘 교차검증(K-S vs Essentia, 위 §)과 청취 스팟체크 외에, 아래 §의 비공식 제3
소스(songbpm.com) 대조가 추가로 확보됐다.

## songbpm.com(Spotify 오디오 분석) 대조 — 44곡

**비공식이지만 독립적인 제3 소스**. `songbpm.com`은 Spotify의 오디오 분석 API가
산출한 key/mode를 그대로 노출하는 사이트다 — 게임 공식 데이터는 아니지만, 우리
두 알고리즘(K-S, Essentia)과는 완전히 다른 파이프라인(Spotify 자체 모델)이라
의미 있는 교차검증이 된다. 표본 10곡 이상 밴드 중 songbpm.com에서 검색 가능한
곡을 밴드당 몇 곡씩 모아 44곡을 확보했다(mugendai_mutype은 커버곡 위주라 Spotify에
전혀 없어 0곡 — 완전 제외).

| 관점 | K-S | Essentia |
|---|---|---|
| key만 정확히 일치 | 52.3% (23/44) | **63.6%** (28/44) |
| mode만 일치(장/단조) | 77.3% (34/44) | 77.3% (34/44, 동률) |
| key+mode 둘 다 일치 | 47.7% (21/44) | **59.1%** (26/44) |

- **반전된 인상**: 사전 수동 대조(4곡, 위 예시들)로는 K-S가 더 정확해 보이는 사례
  (ALIVE (Cover))도 있었지만, 44곡으로 늘리자 **Essentia가 key 정확도·완전일치율
  모두에서 K-S를 10%p 이상 앞선다.** mode만 보면 두 알고리즘이 정확히 동률(77.3%)
  — 위 "mode만 놓고 보면 73.9%(736곡 전체, K-S vs Essentia 상호비교)"와는 별개로,
  이건 "외부 정답 대비" 정확도라는 점에서 의미가 다르다.
- **key 오류의 성격**: key가 틀린 경우 K-S는 71%(완전4·5도 이웃 57%+관계조 14%),
  Essentia는 81%(완전4·5도 50%+관계조 31%)가 음악이론적으로 근접한 조성으로
  어긋난다 — 무작위 오류가 아니라 근친조/이웃조 혼동이라는 지금까지의 가설이 외부
  정답 대비로도 확인됐다. 이 "근접조까지 허용"하는 완화 기준으로 재채점하면
  both-match가 K-S 72.7%, Essentia 75.0%까지 오른다.
- **밴드별 편차**: hello_happy_world(83%)·afterglow(50%)는 상대적으로 안정적,
  roselia(20%)·pastel_palettes(25%)는 both-match가 낮다. 다만 밴드당 1~9곡의
  작은 표본이라 밴드별 수치는 참고 수준.
- **실용적 함의**: key를 하나만 채택해야 한다면 이 결과는 **Essentia 우선 고려**를
  뒷받침한다 — 다만 44곡은 여전히 작은 표본(전체 736곡의 6%)이라 확정적 결론은
  아니며, 표본을 더 늘려 재확인할 가치가 있다.

산출물: `../csv/songbpm_comparison.csv`(44행), `songbpm_comparison_findings.md`.

## morfonica "A minor 쏠림" 심층분석

morfonica 57곡 중 K-S가 A minor로 판정한 17곡(30%) — 밴드 내 최빈 조합 중 유독 튀는
비율이라 원인을 팠다.

- **Essentia 동의율 41%(7/17)** — 밴드 최빈조합 신뢰도 비교에서 전체 10개 밴드 중
  두 번째로 낮음(가장 낮은 mygo는 표본 5곡이라 통계적으로 더 불안정).
- **원인은 절반씩**: cover곡 비율이 관건이었다. morfonica 전체 곡 중 cover는 31.6%인데,
  A minor 판정 17곡 중 cover가 10곡(59%) — 원곡 비율의 거의 2배로 쏠려있다.
  - 대조군: roselia의 "E minor 쏠림"은 정반대로 **오리지널 곡 쪽이 더 쏠림**(23.8% vs
    cover 15.4%) — roselia는 "밴드 자체의 작곡/연주 성향"(록밴드가 기타 치기 좋은
    E minor 선호)으로 설명되지만, morfonica는 그런 메커니즘이 아니다.
  - morfonica의 A minor cover 10곡 중 4곡(Nameless Story·Overdose·祝福·Nevereverland)은
    K-S·Essentia 둘 다 동의(신뢰도도 높음) — 원곡 자체가 실제로 A minor인 발라드류일
    가능성. 나머지 6곡은 Essentia가 D minor/E minor/F major/F minor로 갈림 — 전부
    A minor와 근친 조성으로, K-S 템플릿 매칭의 전형적 약점과 일치.
- **결론**: "morfonica가 이상하리만치 A minor에 쏠려있다"는 절반은 진짜(커버 레퍼토리
  선곡 경향), 절반은 알고리즘 오차. roselia처럼 "밴드 자체의 작곡 성향"으로 설명되는
  케이스는 아니다.

## 베이스 스템 기반 key 검증 (50곡, demucs --two-stems bass, GPU)

**가설**: 베이스 라인만 들으면 으뜸음(tonic)을 더 명확히 판별할 수 있지 않을까 —
seed=42로 뽑은 30곡 + 결정론적으로 추가한 20곡(roselia +1, morfonica +2 포함) 총
50곡의 베이스 스템을 demucs(htdemucs, GPU)로 분리해 같은 K-S 알고리즘을 적용,
전체믹스 결과와 비교.

| 비교 | 30곡 | 50곡 |
|---|---|---|
| 베이스 vs 전체믹스 K-S (정확한 key) | 43.3% | **48.0%** (24/50) |
| 베이스 vs Essentia (정확한 key) | 33.3% | **42.0%** (21/50) |
| 베이스 vs K-S (mode만) | 70% | 72% |
| 베이스 vs Essentia (mode만) | 70% | 74% |
| morfonica+roselia(12곡) 중 | 44.4%(9곡 기준) | 5/12 (41.7%) |

**결론**: 표본을 50곡으로 늘려도 결론은 바뀌지 않는다 — 베이스 스템은 key(정확한
조성) 검증 수단으로 **여전히 신뢰하기 어렵다**(40%대 초반, 전체믹스 K-S·Essentia
어느 쪽과도 안정적으로 안 맞음). 원인 추정: 베이스는 전위·경과음을 자주 연주해
곡 전체의 화성적 중심을 안정적으로 반영하지 못함. mode(장/단조)만 놓고 보면 72~74%로
key 전체 일치율보다 훨씬 높다는 점도 동일하게 재확인됨.

**참고**: 최초 30→50곡 확장 시도는 데이터 처리 로직이 검증된 데뮤스 셰임
(torchcodec 우회 패치)을 재사용하지 않아 전량 실패했었고, 이 과정에서 로컬 GPU
(RTX 4080 Super)가 CPU 전용 torch 때문에 활용되지 못하고 있었다는 것도 함께
발견되어 CUDA 빌드로 교체했다(이후 곡당 처리시간 약 45초→10초로 단축).

산출물: `out/bass_key_validation/bass_key_validation.csv`(50행), `REPORT.md`.

## 모드 스케일(교회선법) 확장 실험 (50곡)

**가설**(연구자 제안): roselia 같은 고딕록/메탈 성향 밴드는 major/minor 두 선법 외에
Phrygian/Aeolian 등을 자주 써서 mode 일치율이 낮게 나오는 것 아닐까 — K-S major/minor
프로파일을 5개 교회선법(Dorian/Phrygian/Lydian/Mixolydian/Locrian)까지 확장(12키 x 7모드
= 84템플릿)해 재분석. bass_key_validation과 동일 표본(30→50곡 확장)에 적용.

**⚠️ 방법론 한계**: major/minor 프로파일은 실제 청취실험(probe-tone) 검증값이지만,
나머지 5개 선법은 그런 실증 데이터가 없다. major/minor 프로파일에서 각 모드의 특징음
가중치를 맞바꾸는 휴리스틱으로 근사했다 — 통계적으로 검증된 값이 아니라 참고용.

| 지표 | 30곡 | 50곡 |
|---|---|---|
| major/minor 아닌 모드로 판정 | 46.7% | 42.0% (21/50) |
| 장/단조 계열(family) 기준 기존 K-S와 일치 | 96.7% | 94.0% |
| 신뢰도(confidence) 평균 | 0.415 | 0.405 (기존 24템플릿 K-S는 0.526) |

표본을 늘려도 "다중비교로 과대추정됐을 것"이라는 우려와 달리 non-major/minor 비율은
오히려 소폭 하향 안정화(46.7%→42.0%)됐다 — 우연한 튐이 아니라 어느 정도 재현되는
패턴으로 보인다.

- **roselia 6곡 결과**: mixolydian·ionian·lydian·ionian(장조 계열 4곡), dorian(단조
  계열 1곡), **그리고 신규 추가곡(idx 631 "Proud of oneself")에서 마침내 Phrygian
  등장**. 즉 30곡 때는 "가설이 뒷받침 안 됨"이었다가, 표본을 늘리자 Phrygian 사례가
  나왔다 — 여전히 6곡 중 1곡뿐이라 확정적이진 않지만, 방향성은 완전히 기각하기보다
  추가 표본이 더 필요하다는 쪽으로 기운다.
- **morfonica 6곡 결과가 더 흥미롭다**: minor로 분류됐던 4곡 중 3곡(祝福·かくれんぼ·
  Nameless Story)이 **전부 Phrygian**으로 판정, 나머지 1곡(メランコリックララバイ)은
  Dorian, 진짜 Aeolian(순수 자연단조)은 flame of hope 1곡뿐이었다. 즉 앞서 "morfonica
  A minor 쏠림"으로 봤던 것 중 상당수가 실제로는 **일반 단조가 아니라 Phrygian
  특유의 b2 색채를 띠는 곡들**이었을 가능성 — major/minor 2지선다 틀 자체가 이
  밴드에는 안 맞았을 수 있다는 새로운 가설.
- 다음 단계 후보: roselia·morfonica 각각 전체(89곡/57곡)로 표본을 넓혀 이 패턴이
  유지되는지 확인(현재는 미착수).

산출물: `../csv/modal_key_validation.csv`(50행), `modal_key_validation_REPORT.md`.
생성 스크립트: `src/extract_key_modal.py`(기존 `extract_key_ks.py`의 템플릿 매칭·
다수결 함수를 그대로 import해 재사용).

## 종합 결론 및 다음 단계

1. **key(정확한 조성) 절대값은 신뢰도가 낮다**(39.4% 불일치) — 곡 간 비교나 선곡
   로직에 쓸 때는 mode(장/단조, 73.9% 일치)까지만 활용하는 게 안전.
2. roselia·raise_a_suilen은 mode 자체가 불안정(63~67%)해 우선순위 청취 스팟체크 대상.
3. morfonica의 A minor 쏠림은 커버곡 선곡 경향 + 알고리즘 오차가 섞인 것으로 설명됨.
4. 베이스 스템은 key 신뢰도를 끌어올리는 데 유의미하게 기여하지 못함(48%대 정체) —
   **50곡 청취 스팟체크가 여전히 유일한 확실한 검증 수단**으로 남아있음
   ([[key-profile-bug-status]] 인계 대기 중).
5. 모드 스케일 확장은 표본을 늘려도 안정적으로 재현되는 패턴(roselia Phrygian 등장,
   morfonica 단조곡 다수가 실제로는 Phrygian)을 보여, **major/minor 2지선다 틀 자체가
   일부 밴드엔 부적합할 수 있다는 가설이 완전히 기각되진 않았다** — 다만 방법론적으로
   실증 검증되지 않은 휴리스틱 템플릿이라는 한계는 여전하므로, 전체 표본 확장 또는
   청취 검증으로 재확인 필요.
6. **인프라 개선(부수 발견)**: 로컬 GPU(RTX 4080 Super)가 CPU 전용 torch 때문에 활용
   못 되고 있던 것을 이번에 발견해 CUDA 빌드(torch 2.6.0+cu124)로 교체 — demucs 처리
   속도가 곡당 약 45초→10초로 단축됨. 이 환경은 miniconda 공용 Python이라 다른 topic
   (mfcc_analysis, vector_embedding 등)의 오디오 분리 작업에도 동일하게 적용된다.
7. **songbpm.com(Spotify) 외부 대조 44곡**: Essentia가 K-S보다 key 정확도(63.6% vs
   52.3%)·완전일치율(59.1% vs 47.7%) 모두 우세 — key를 하나만 쓴다면 Essentia
   우선 고려. key 오류의 71~81%가 완전4·5도 이웃/관계조 혼동으로, 무작위가 아닌
   체계적 오류임이 외부 정답 대비로도 확인됨.
8. 스크립트/데이터 무결성: 2026-08-01 idx 재정렬(신규 75곡, `file_idx` 컬럼 분리)
   이후 최신 736곡 기준으로 위 통계 전부 갱신됨 — CONVENTIONS.md "idx와 file_idx" 절
   참고.

## 관련 산출물

- `../csv/key_raw.csv` — 736곡 K-S/Essentia key 원시 결과
- `metadata.md`, `../timeseries/metadata.md` — 컬럼 메타데이터
- `../bass_key_validation/` — 베이스 스템 검증(50곡)
- `../csv/modal_key_validation.csv`, `modal_key_validation_REPORT.md` — 모드 스케일 확장 실험(50곡)
- `../csv/songbpm_comparison.csv`, `songbpm_comparison_findings.md` — songbpm.com(Spotify) 외부 대조(44곡)
- `src/extract_key_ks.py`, `src/extract_key_essentia.py` — 원본 추출 스크립트
- `src/extract_key_modal.py` — 모드 스케일 확장 스크립트
- `src/_demucs_run.py` — torchcodec 우회 demucs 실행 셰임(GPU `-d cuda` 지원)
- `src/_expand_bass_50.py` — 베이스 검증 30→50곡 확장 스크립트(GPU demucs 재사용)
