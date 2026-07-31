# method-1 — §2(ground truth 확장) 청취 없이 가능한 준비 작업

## 이 방법이 무엇인지
`framework.md` §2의 실행 준비 단계. 청취가 필요한 실제 라벨링 전에, (a) 기존 라벨끼리
대조해서 결론이 나는 부분(party↔intensity 겹침)과 (b) 라벨링 대상 후보곡 선정(valence·
pathos)은 기존 데이터만으로 끝낼 수 있어 먼저 처리했다.

## 어떻게 실행했는지
1. `check_party_intensity_overlap.py` — `data/ground_truth_labels.csv`의 party/intensity
   라벨을 곡 단위로 조인하고 `audio_feats.csv`의 `energy_full`과 대조. 청취 불필요.
2. `build_valence_candidates.py` — `audio_feats.csv`에서 `mode_score` 극단(밴드당 최대 3곡
   상한)을 뽑아 `out/valence_candidates.csv` 생성 + report/02의 기존 반례 앵커 3곡 강제 포함.
   청취는 다음 세션이 이 CSV의 `valence_rating_1to10`을 채우면서 진행.
3. `build_pathos_candidates.py` — `mood_warmth/candidates_worksheet.csv`의 29곡을 그대로
   재사용해 `out/pathos_candidates.csv` 생성(새 표집 안 함, 곡 선정 비용 재사용). 청취는
   다음 세션이 `pathos_rating_0to10`을 새 질문("애절하나 위로되는가")으로 채우면서 진행.

실행(모두 `python <스크립트>`, 인코딩 문제 시 `PYTHONIOENCODING=utf-8` 접두):
```
python check_party_intensity_overlap.py
python build_valence_candidates.py   # 보류(파기 아님) — framework.md §2e 참조
python build_pathos_candidates.py    # 보류(파기 아님) — framework.md §2e 참조
python build_gems9_pilot_candidates.py
```

## GEMS-9 파일럿 (2026-07-22 방법론 전환)

4. `build_gems9_pilot_candidates.py` — `audio_feats.csv`에서 밴드당 최대 3곡(20곡 이상
   밴드는 `energy_full` 최저/중간/최고, 소규모 카테고리는 있는 만큼)을 뽑아
   `out/gems9_pilot_candidates.csv`(35곡) 생성. 대표구간(초)·GEMS-9 채점은 사용자가 직접
   채운다. 상세 설계는 `framework.md` §2e, 실험 프로토콜 원본은 `notes/gems_methodology.md`.

### GEMS-9 항목 정의 (채점 시 참고, Zentner et al. 2008)

| 컬럼 | 한글 명칭 | 상위요인 |
|---|---|---|
| `wonder` | 경이/경탄 | Sublimity |
| `transcendence` | 초월/숭고함 | Sublimity |
| `tenderness` | 다정함/애틋함 | Sublimity |
| `nostalgia` | 향수/그리움 | Sublimity |
| `peacefulness` | 평온함 | Sublimity |
| `power` | 웅장함/강렬함 | Vitality |
| `joyful_activation` | 활기찬 기쁨 | Vitality |
| `tension` | 긴장/불안 | Unease |
| `sadness` | 슬픔 | Unease |

상위요인(Sublimity/Vitality/Unease)은 참고용이며 미리 전제하지 않는다 — §3 스크리닝에서
데이터가 실제로 어떻게 묶이는지 사후에 확인한다.

## 청취용 도구 2종 (2026-07-22)

- **Tool 1 — `segment_picker_tool.html`**: 35곡의 대표구간(IN/OUT)을 유튜브 영상을 직접
  들으며 지정하는 도구. 사용법은 `segment_picker_tool_guide.md`.
- **Tool 2 — `segment_survey_tool.html`**: 지정된 구간만 재생/정지 버튼으로 통제해
  들려주고 GEMS-9 9항목을 1~5점으로 채점하는 도구. 영상 자체는 클릭으로 탐색 불가(재생/
  정지 버튼으로만 제어) — `gems_methodology.md` §3.1 "동일 구간 통제" 반영. 사용법은
  `segment_survey_tool_guide.md`.
- **`build_gems9_survey_data.py`**: `out/gems9_pilot_candidates.csv`를 읽어
  `segment_survey_tool.html`의 곡 데이터 블록(`<script type="application/json"
  id="songs-data">`)만 갱신한다. 구간(`excerpt_start_sec`/`excerpt_end_sec`)이 비어있는
  곡은 폴백(인트로 0~30초)으로 채우고 `isFallback:true`를 표시 — Tool 1로 구간 설정을
  끝내고 CSV를 갱신한 뒤 이 스크립트를 다시 돌리면 Tool 2가 자동으로 정식 구간을 쓰게
  된다(HTML을 손으로 고칠 필요 없음).

두 도구 모두 유튜브 IFrame API를 쓰므로 `file://`로 직접 열지 말고 로컬 서버로 실행할 것
(각 가이드 문서 참조). claude.ai 아티팩트로 열면 iframe이 동작하지 않을 수 있어 로컬 실행이
기본 경로다.

## n≥20 확대 라운드용 — 구글폼 자동 생성 (2026-07-22)

Tool 2(커스텀 HTML)는 n=1 파일럿용. n≥20 다중 응답자 라운드는 응답 자동 집계(구글시트)가
가능한 **구글폼**으로 전환한다 — 단 구간 끝점 자동정지는 지원 안 되고 문구로 권고만 함
(트레이드오프, 사용설명서 참조).

- **`gems9_google_form.gs`**: Google Apps Script(`script.google.com`)에 붙여넣어 실행하면
  35곡짜리 폼을 한 번에 생성. 사용법은 `gems9_google_form_guide.md`.
- `build_gems9_survey_data.py`가 이 파일의 `SONGS` 배열도 함께 갱신한다(HTML과 동일한
  재생성 흐름) — Tool 1로 구간 확정 후 이 스크립트만 다시 돌리면 됨.

## n≥20 라운드 곡 샘플링 재설계 (2026-07-23, 통계 자문 반영)

기존 에너지 극단추출 방식의 confound 문제가 제기되어, 통계학자 페르소나 서브에이전트와
3라운드 검증을 거쳐 곡 샘플링을 처음부터 다시 설계했다. 전체 대화와 최종 절차는
`report/04-n20_sampling_consult.md`, 분석 스펙 동결본은 `notes/n20_prereg.md`, 절차
플로차트는 `fig/n20-screening-flowchart.webp`(한글판)·`fig/n20-screening-flowchart-en.webp`
(영문판) 참고.

- **`build_gems9_n20_candidates.py`**: 모집단 필터(밴드 15곡 미만·`various_artists` 제외)
  → 전체카탈로그 피쳐 차원축소(상관 클러스터링, 19→17개 대표 피쳐) → PC1 기준 밴드×삼분위
  균형표집으로 본표본 70곡 + 동일 시드로 disjoint 홀드아웃 25곡(봉인) 추출.
  `out/gems9_n20_candidates.csv`, `out/gems9_n20_holdout_sealed.csv`,
  `out/gems9_n20_representative_features.csv` 생성.
- **`assign_rater_blocks.py`**: 본표본 70곡을 겹치는 블록 5개(30곡씩)로 나누고 응답자
  ~22명을 블록에 배정 — 곡별 최소 응답자 수·연결성 사후 검증.
  `out/gems9_n20_rater_block_assignment.csv`, `out/gems9_n20_block_definitions.csv` 생성.
- **`analyze_gems9_n20.py`**: (실제 응답 수집 후) 혼합모형(고정효과 rater+랜덤절편 song)으로
  평정자 효과 제거 → 가중 Spearman + 부트스트랩 CI + BH-FDR → 홀드아웃 확증(부호일치·
  CI겹침·|rho|≥0.3). 실제 응답 CSV(`out/gems9_n20_responses.csv`)가 없으면 합성데이터로
  파이프라인 배선만 검증하는 스모크테스트가 돈다.
- **`draw_n20_screening_flowchart.py`**: 위 절차 전체를 `fig/n20-screening-flowchart.webp`
  (한글판)·`fig/n20-screening-flowchart-en.webp`(영문판)로 시각화(PRISMA 스타일, 화살표는
  가로·세로만 사용하고 제외 분기는 메인 흐름 화살표 중간에서 T자로 갈라지는 형태).

**다음 단계(미완)**: 불완전블록 설계라 `gems9_google_form.gs`처럼 폼 하나에 전곡을 넣는
방식이 안 맞는다 — 블록 5개 각각에 대해 별도 구글폼을 생성하도록
`build_gems9_survey_data.py`/`gems9_google_form.gs`를 확장해야 응답자에게 배정된 블록
링크를 보낼 수 있다. 아직 구현 안 됨.
