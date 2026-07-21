# Essentia 교차검증 — 661곡 전체, 일치율 및 불일치 유형 분석 (report/06 §7-3 후속)

**세션일**: 2026-07-21~22. report/06 §7-3이 인계한 "잔여 장/단조 혼동 조사"를 진행했다.
tunebat 스크레이핑 시도는 두 가지 이유로 기각했다: (1) tunebat도 진짜 정답이 아니라
Spotify의 또 다른 오디오 추정 알고리즘일 뿐이라 "정답 대조"가 아니라 "또 다른 추정과의
비교"에 불과하고, (2) tunebat이 자동화된 요청(WebFetch)에 403을 반환해 스크레이핑 자체가
순탄치 않다. 대신 **Essentia(독립적으로 구현된 오픈소스 알고리즘)와 우리 파이프라인의
일치율**을 661곡 전체에서 측정해, 일치하는 곡은 신뢰도를 높이고 불일치하는 곡만 사람이
직접 들어야 할 후보로 추리는 방식을 택했다.

## 1. 방법

- `essentia_streaming_key.exe`(v2.1_beta5, Windows 정적 바이너리) 다운로드 후
  **subprocess로 호출**(라이브러리 직접 import 금지 — AGPL-3.0 라이선스 위생, report/06 §7
  지침 준수). 661곡 전체에 대해 곡당 key/key_scale/key_strength를 추출(20.9분 소요).
- 결과를 `topic/audio_feats_analysis/out/essentia_key.csv`에 저장, `audio_feats.csv`의
  `est_key`와 `tag` 기준으로 병합(`key_agreement_full.csv`).
- Essentia 호출 스크립트 자체는 report/06 §7 지침에 따라 repo에 커밋하지 않음(세션
  스크래치에만 보관). 산출 CSV만 커밋.

## 2. 전체/밴드별 일치율

**전체 일치율: 55.4% (366/661)**

| 밴드 | 일치율 | n |
|---|---|---|
| various_artists | 80.0% | 5 |
| afterglow | 70.8% | 72 |
| hello_happy_world | 61.1% | 72 |
| morfonica | 61.4% | 57 |
| ave_mujica | 58.6% | 29 |
| poppin_party | 55.6% | 115 |
| pastel_palettes | 55.4% | 74 |
| mygo | 50.0% | 44 |
| roselia | 49.4% | 89 |
| raise_a_suilen | 44.3% | 79 |
| mugendai_mutype | 34.8% | 23 |

무작위로 24개 조성 중 일치할 확률(≈4.2%)보다 훨씬 높아 신호는 분명하지만, 절반 가까이
불일치한다는 건 두 알고리즘 모두 K-S/템플릿-상관계수 계열이라 공통 약점을 공유한다는
뜻이다(§3에서 확인).

## 3. 불일치 유형 분류 — 대부분 "예상된" 혼동

295개 불일치를 서클오브피프스(circle of fifths) 거리 기준으로 분류:

| 유형 | 정의 | 건수 | 비율 |
|---|---|---|---|
| near (근접조) | 한 칸 차이, 7음 중 6음 겹침(예: Amin↔Gmaj) | 160 | 54.2% |
| relative (관계조) | 서클 위 같은 위치, 장/단조만 다름(7/7 겹침, 예: Amin↔Cmaj) | 58 | 19.7% |
| parallel (병행조) | 근음은 같고 장/단조만 다름(예: Cmaj↔Cmin) | 27 | 9.2% |
| **far (설명 안 됨)** | 위 세 유형 어디에도 안 속함 | **50** | **17.0%** |

**설명 가능한 유형(near+relative+parallel) 합계: 83.0%(245/295).** 즉 불일치의 대부분은
"두 독립 알고리즘이 서로 다른 구현임에도 같은 종류의 구조적 함정(피치클래스 집합이 대부분
겹치는 조성 간 판별 불가)에 빠진 것"으로 설명된다 — report/06 §4의 예측, report/08(케이던스
파일럿 실패)이 시사한 바와 일치.

부가 확인: `mode_score`(우리 자체 신뢰도 지표)의 절대값 평균이 `agree`군(0.160)에서 가장
높고 `far`군(0.102)에서 가장 낮다 — 우리 자체 지표가 실제로 신뢰도를 어느 정도 반영한다는
뜻이라 위안이 된다.

## 4. 사람이 확인해야 할 우선순위 — "far" 50곡

전체 661곡을 다 들을 필요 없이, **"설명 안 되는" 50곡만** 사람이 직접 들어서 어느 쪽이
맞는지(혹은 둘 다 틀렸는지) 확인하는 게 비용 대비 합리적이다. 목록은
`topic/audio_feats_analysis/out/key_far_disagreement_50.csv`(`mode_score` 절대값 오름차순
정렬 — 우리 알고리즘이 자체적으로도 확신 없어했던 곡부터).

상위 10곡 예시:
| 곡 | 밴드 | 우리 est_key | Essentia |
|---|---|---|---|
| Symbol IV : Earth | ave_mujica | D#maj | Gmaj |
| 回層浮 | mygo | C#maj | G#min |
| EXIST | raise_a_suilen | Gmaj | Cmin |
| mind of Prominence | raise_a_suilen | A#min | D#maj |
| This game (Cover) | roselia | F#min | Emin |
| わたしまちがいさがし | morfonica | Emin | Fmaj |
| みゅーたんとミュータント | mugendai_mutype | Dmaj | A#maj |
| ブルームブルーム | morfonica | Gmin | F#min |
| **Angel's Ladder** | morfonica | Amin | **A#maj** |
| CORUSCATE -DNA- | raise_a_suilen | Gmin | Cmaj |

**참고**: report/06·07에서 tunebat으로 확인했던 Angel's Ladder(실제 B♭ major)가 이 목록에
있다 — Essentia의 답(A#maj = B♭ major 이명동음)이 tunebat과도 일치한다. 이건 tunebat이
"정답"이라서가 아니라(§서두 참조) Essentia·Spotify 두 독립 시스템이 우리와 다른 답으로
수렴했다는 추가 정황일 뿐이며, 여전히 최종 확인은 사람이 들어야 한다.

## 5. 결론 및 다음 단계

1. **일치하는 366곡**은 두 독립 알고리즘이 합의했으므로 상대적으로 신뢰도가 높다고 간주.
2. **근접조/관계조/병행조 불일치 245곡**은 상관계수 기반 방법론의 구조적 한계로, 추가
   알고리즘 개선으로는 풀기 어렵다(report/08의 케이던스 시도 실패가 방증). 이 곡들은
   "확신 없음"으로 표시하고 넘어가는 게 현실적.
3. **far 불일치 50곡만 사람이 직접 청취 확인** — `key_far_disagreement_50.csv` 순서대로
   진행 권장. 이 리스트는 chord_progression 리서치의 "청취 스팟체크" 인계(`topic/chord_progression/HANDOFF.md`)
   와 같은 방식으로 별도 세션에 넘길 수 있음.
4. `songs_master.csv`/`key_proxies` 반영 여부는 report/07 §4 결정(반영 보류) 그대로 유지 —
   이번 조사도 연구 범위이며 프로덕션 데이터는 건드리지 않음.

## 6. 산출물
- `topic/audio_feats_analysis/out/essentia_key.csv` (661행, Essentia 원본 결과)
- `topic/audio_feats_analysis/out/key_agreement_full.csv` (661행, est_key·essentia_key 병합 +
  일치 여부)
- `topic/audio_feats_analysis/out/key_far_disagreement_50.csv` (사람 청취 확인 대상 50곡,
  `mode_score` 절대값 오름차순)
- Essentia 바이너리(`essentia_streaming_key.exe`)와 호출 스크립트는 report/06 §7 지침에 따라
  커밋하지 않음(로컬에만 보관)
