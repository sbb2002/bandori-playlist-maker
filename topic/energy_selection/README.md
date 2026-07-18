# energy_selection: LLM 에너지 파라미터 해석 프롬프트 튜닝

> **상태(2026-07-18)**: ✅ 실험 완료 — **`candidate_AB` 채택 권고**(배포 미반영, 제안 단계).
> 200회 실행 결과 카테고리 B(절대시간 피크지정)에서 baseline 0.278 → candidate_B 0.956로
> 가장 크게 개선, 회귀(C/D) 없음 확인. 상세: `report/01-energy_selection_prompt_tuning.md`.
> 프로덕션 `prompt.py`의 `SYSTEM_PROMPT`는 아직 변경하지 않았다 — 반영은 별도 승인 필요.

배포판에서 사용자가 에너지 진행을 LLM에 맡기면(수동 그래프 편집 아닌 자연어 경로) 구간별
에너지 값을 부정확하게 산출하는 실패 사례 2건이 관찰됐다(`background.md`). 코드 감사 결과
결정적 로직(`energy.py`, `selection.py`, `parse_mood()`)에는 버그가 없고 원인은
`src/backend/app/adapters/prompt.py`의 `SYSTEM_PROMPT`가 두 가지 요청 유형(①양자택일/대조
표현, ②절대시간 피크 지정)을 충분히 다루지 못하는 데 있음을 확정했다(`DESIGN.md` §1).

이 실험은 순수 LLM 프롬프트 A/B 테스트로, 오디오·임베딩 파이프라인이 필요 없어 다른 topic들보다
훨씬 저비용·고속이다 — 규칙기반 채점(사람 청취 불필요)으로 baseline 대비 개선 프롬프트 2종(+결합
1종)을 비교한다.

**설계 문서**: `DESIGN.md` (필독 — 실패모드 분석, 판정 기준, 쿼리셋, 채점 방법 전체)

---

## 구현 시 실행 순서 (DESIGN.md §7)

```bash
cd C:/Users/User/Documents/pyworks/bandori-playlist-maker
$env:PYTHONIOENCODING = "utf-8"
C:/Users/User/miniconda3/envs/warmth/python.exe topic/energy_selection/01_run_variants.py
C:/Users/User/miniconda3/envs/warmth/python.exe topic/energy_selection/02_score.py
C:/Users/User/miniconda3/envs/warmth/python.exe topic/energy_selection/03_compare.py
```

### Groq API 키
`work/groq.key` 파일 또는 `GROQ_API_KEY` 환경변수(다른 topic들과 동일 관례).

### 산출물
- `out/raw_responses.csv` — 4 variant × 10쿼리 × 5트라이얼 원시 응답
- `out/scored.csv` — 규칙기반 채점 결과
- `out/comparison_summary.csv` + 콘솔 리포트 — variant별 카테고리 평균, Wilcoxon 결과

## 참고 문서
- `DESIGN.md` — 전체 설계(구현의 원본)
- `background.md` — 최초 문제 제기(실패 사례 2건 원문)
- `src/backend/app/adapters/prompt.py` (main 브랜치) — 튜닝 대상 `SYSTEM_PROMPT`
