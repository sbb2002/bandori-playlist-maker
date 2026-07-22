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
