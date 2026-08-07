"""stage_params 신뢰도 스윕 — 실제 배포 모델(GROQ_MODEL)로 프롬프트 10개 x 3회 = 30콜.

리포 루트에서 실행: `python docs/research/2026-08-04_stage_params_reliability/sweep_gpt_oss.py`
필요 환경: 리포 루트 `.env`에 GROQ_API_KEY(+ GROQ_MODEL, 없으면 groq_adapter 기본값), 그리고
SONGS_CSV(선택, 없으면 `data` 브랜치 원격 fetch를 시도하는 song_repo.load_songs 기본 동작 — 로컬
`data` 브랜치 워크트리를 쓰려면 SONGS_CSV 환경변수로 지정).

산출: 같은 폴더에 sweep_results.json(원본) — build_csv.py로 call_summary/stage_detail/
stats_summary/per_prompt_stats CSV 4종으로 가공한다.
"""

import sys
import os
import json
import time
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "backend"))
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_ENV_PATH = os.path.join(_REPO_ROOT, ".env")
if os.path.exists(_ENV_PATH):
    for line in open(_ENV_PATH, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

from app.adapters.groq_adapter import GroqMoodInterpreter, DEFAULT_BASE_URL, DEFAULT_MODEL
from app.ports.mood_port import LLMRateLimitError, LLMUpstreamError, MoodInterpretationError
from app.repo.song_repo import load_songs

REAL_MODEL = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
SONGS_CSV = os.environ.get("SONGS_CSV")  # None이면 song_repo가 data 브랜치 원격 fetch 시도
songs = load_songs(SONGS_CSV)
pool = [s for s in songs if s.eligible_band]

AUDIO_FEATURE_COLS = ["valence", "lufs_integrated", "lra", "danceability_norm", "instr_stem_ratio", "speech_median"]


def group_stats(items):
    out = {}
    for f in AUDIO_FEATURE_COLS:
        vals = [getattr(s, f) for s in items if getattr(s, f) is not None]
        if not vals:
            continue
        out[f] = {"min": min(vals), "max": max(vals), "mean": statistics.fmean(vals),
                   "median": statistics.median(vals), "std": statistics.pstdev(vals) if len(vals) > 1 else 0.0}
    return out


feature_stats = {"전체": group_stats(pool)}
energies = [s.energy for s in pool]
energy_stats = {"min": min(energies), "max": max(energies), "mean": statistics.fmean(energies),
                 "std": statistics.pstdev(energies)}

# 실사용을 대표할 만한 10개 프롬프트(카테고리 다양화: 차분/파티/슬픔/운동/드라이브/집중/수면/비/청소/쿨다운)
PROMPTS = [
    "더운 저녁을 식혀주는 5단계 노래. 마지막에 차분한 구간을 길게 해줘.",
    "신나는 파티, 텐션 최고조로 끌어올려줘 60분",
    "우울하고 무거운 밤, 조용히 침잠하는 발라드만",
    "아침 조깅용 30분, 점점 빨라지는 흐름",
    "주말 드라이브에 어울리는 밝은 플레이리스트 45분",
    "시험공부 집중용 잔잔한 배경음악 90분",
    "잠들기 직전 듣는 아주 조용한 곡",
    "비 오는 날 창밖 보며 듣는 잔잔한 노래",
    "혼자 청소하면서 듣는 무난한 배경음악",
    "유산소 운동 마무리, 격렬했다가 서서히 식는 흐름 40분",
]

interp = GroqMoodInterpreter(
    api_key=os.environ["GROQ_API_KEY"], model=REAL_MODEL, base_url=DEFAULT_BASE_URL,
    max_retries=6, retry_base=1.5,
)

records = []
rate_limit_events = 0
total = len(PROMPTS) * 3
n = 0
for p_idx, prompt in enumerate(PROMPTS):
    for attempt in range(3):
        n += 1
        rec = {"prompt_idx": p_idx, "prompt": prompt, "attempt": attempt}
        try:
            params = interp.interpret(prompt, energy_stats=energy_stats, feature_stats=feature_stats)
            rec["ok"] = True
            rec["stage_count"] = params.stage_count
            rec["brightness"] = params.brightness
            rec["start_energy"] = params.start_energy
            rec["end_energy"] = params.end_energy
            rec["stage_params_present"] = params.stage_params is not None
            rec["stage_params"] = params.stage_params
            rec["stage_minutes"] = params.stage_minutes
        except LLMRateLimitError as e:
            rate_limit_events += 1
            rec["ok"] = False
            rec["error"] = f"RATE_LIMIT: {e}"
        except (LLMUpstreamError, MoodInterpretationError) as e:
            rec["ok"] = False
            rec["error"] = f"{type(e).__name__}: {e}"
        records.append(rec)
        print(f"[{n}/{total}] prompt={p_idx} attempt={attempt} ok={rec.get('ok')} "
              f"stage_params_present={rec.get('stage_params_present')}", flush=True)
        time.sleep(4)  # TPM 페이싱

out_path = os.path.join(os.path.dirname(__file__), "sweep_results.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({"records": records, "rate_limit_events": rate_limit_events}, f, ensure_ascii=False, indent=2)

print("DONE. rate_limit_events =", rate_limit_events)
