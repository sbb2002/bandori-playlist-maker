# boundary_tension 회귀가드 완화 — 로컬 검증 가이드

이 브랜치(`hotfix/boundary-tension-relative-threshold`, 커밋 `a838f1b`)는
`test_boundary_tension_continuity_is_smooth`(`test_integration.py`)의 판정 기준을 절대
임계값(0.44)에서 **상대 개선폭 기준**(비율 ≤ 0.80)으로 바꿨다. 배경·근거는 `test_integration.py`
해당 테스트의 docstring 참조. 이 문서는 다른 로컬에서 이 변경을 검증하는 절차만 다룬다.

## 1. 환경 준비

```bash
cd src/backend
python -m venv venv
source venv/Scripts/activate   # Windows Git Bash. PowerShell은 venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install pytest
```

## 2. 전체 테스트 통과 확인

```bash
cd ..            # src/ 로 이동 (pytest는 tests/ 를 이 위치에서 인식)
python -m pytest tests/ -q
```

**기대 결과**: 186 passed, 실패 없음. 실패하면 "완료"로 보고하지 말고 실패 그대로 보고할 것
(`src/tests/README.md` 규칙 5).

## 3. 이번 변경 테스트만 상세히 확인

```bash
python -m pytest tests/test_integration.py -q -k boundary_tension -v
```

통과 시 별다른 출력이 없다. **일부러 실패시켜서 판정 로직이 맞는지 보고 싶다면**, 테스트 파일의
`assert ratio <= 0.80` 줄을 잠깐 `assert ratio <= 0.01`처럼 바꿔서 실행 — 실패 메시지에
`actual=... random_baseline=... ratio=...` 세 값이 출력된다. 확인 후 반드시 `0.80`으로 되돌릴 것
(커밋하지 말 것).

## 4. (선택) 재현 시뮬레이션 — 스냅샷이 바뀌어도 안정적인지 재확인

과거 절대 임계값(0.44)은 곡 2개만 빠져도 실측치가 급변했었다(2026-07-13 사건). 새 상대 지표가
정말 스냅샷 변경에 강건한지 직접 보고 싶다면 아래 스크립트를 `src/backend/`에 임시로 만들어
실행한다(실행 후 삭제):

```python
# src/backend/_verify_robustness.py (검증 후 삭제)
import random, statistics, csv, sys
from pathlib import Path
sys.path.insert(0, ".")
from app.domain.models import MoodParameters
from app.domain.selection import build_setlist
from app.repo.song_repo import load_songs

FIXTURE = Path("../tests/fixtures/songs_master.csv")

def quiet_params():
    return MoodParameters(brightness=0.1, start_energy=0.15, end_energy=0.15,
                           stage_count=3, target_minutes=60, interpretation_summary="")

def mean_gap(by_idx, order):
    return statistics.mean(abs(by_idx[a.idx].outro_energy - by_idx[b.idx].intro_energy)
                            for a, b in zip(order, order[1:]))

def ratio_for(songs, seed=0):
    by_idx = {s.idx: s for s in songs}
    sl = build_setlist(songs, quiet_params(), target_seconds=60*60, rng=random.Random(seed))
    actual = mean_gap(by_idx, sl.picks)
    brng = random.Random(12345)
    shuffled = list(sl.picks)
    gaps = []
    for _ in range(200):
        brng.shuffle(shuffled)
        gaps.append(mean_gap(by_idx, shuffled))
    return actual / statistics.mean(gaps)

with FIXTURE.open(encoding="utf-8", newline="") as f:
    idxs = [int(r["idx"]) for r in csv.DictReader(f) if r["eligible_band"].strip().lower() == "true"]

rng = random.Random(1)
for trial in range(5):
    drop = set(rng.sample(idxs, 2))
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    kept = [r for r in lines[1:] if int(r.split(",", 1)[0]) not in drop]
    tmp = Path("_tmp_verify.csv")
    tmp.write_text(lines[0] + "\n" + "\n".join(kept) + "\n", encoding="utf-8")
    r = ratio_for(load_songs(tmp))
    print(f"trial {trial}: dropped={sorted(drop)} ratio={r:.4f}  ({'PASS' if r <= 0.80 else 'FAIL'})")
    tmp.unlink()
```

```bash
cd src/backend && source venv/Scripts/activate && python _verify_robustness.py
rm _verify_robustness.py
```

**기대 결과**: 5개 트라이얼 모두 `ratio` 대략 0.3~0.7대에서 `PASS`. (2026-07-24 실측: 0.28~0.72
범위, 80회 시뮬레이션 기준 — 자세한 수치는 이 hotfix 커밋 메시지 참조.)

## 5. 검증 후

모두 통과했다면 이 파일을 지우고(임시 검증 문서, PR에는 불필요) 사용자에게 결과를 보고한다.
다음 단계는 `git-rules.md`의 hotfix 절차(PR 열기 직전 Patch 버전 태깅 → PR 오픈)이며, 이건
사용자 확인 후 진행 — 임의로 태깅·PR 오픈하지 말 것.
