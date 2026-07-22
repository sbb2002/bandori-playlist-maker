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
python build_valence_candidates.py
python build_pathos_candidates.py
```
