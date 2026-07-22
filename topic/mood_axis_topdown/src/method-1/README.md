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
