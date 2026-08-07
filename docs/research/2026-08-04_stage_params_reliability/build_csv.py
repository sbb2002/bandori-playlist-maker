"""sweep_results.json(sweep_gpt_oss.py 산출)을 CSV 4종으로 가공한다.

리포 루트에서 실행: `python docs/research/2026-08-04_stage_params_reliability/build_csv.py`
"""

import json
import csv
import os
import statistics

_DIR = os.path.dirname(__file__)
SWEEP_JSON = os.path.join(_DIR, "sweep_results.json")

data = json.load(open(SWEEP_JSON, encoding="utf-8"))
records = data["records"]

FIELDS = ["valence", "lufs_integrated", "lra", "danceability_norm", "instr_stem_ratio", "speech_median"]

call_rows = []
stage_rows = []

for rec in records:
    call_rows.append({
        "prompt_idx": rec["prompt_idx"],
        "prompt": rec["prompt"],
        "attempt": rec["attempt"],
        "ok": rec.get("ok"),
        "error": rec.get("error", ""),
        "stage_count": rec.get("stage_count", ""),
        "brightness": rec.get("brightness", ""),
        "start_energy": rec.get("start_energy", ""),
        "end_energy": rec.get("end_energy", ""),
        "stage_params_present": rec.get("stage_params_present", ""),
        "stage_minutes": json.dumps(rec.get("stage_minutes"), ensure_ascii=False) if rec.get("stage_minutes") is not None else "",
    })
    sp = rec.get("stage_params")
    sm = rec.get("stage_minutes") or []
    if sp:
        for i, stage in enumerate(sp):
            row = {
                "prompt_idx": rec["prompt_idx"],
                "prompt": rec["prompt"],
                "attempt": rec["attempt"],
                "stage_index": i,
                "stage_minutes": sm[i] if i < len(sm) else "",
            }
            for f in FIELDS:
                row[f] = stage.get(f) if stage else None
            stage_rows.append(row)

with open(os.path.join(_DIR, "call_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(call_rows[0].keys()))
    w.writeheader()
    w.writerows(call_rows)

with open(os.path.join(_DIR, "stage_detail.csv"), "w", newline="", encoding="utf-8-sig") as f:
    fieldnames = ["prompt_idx", "prompt", "attempt", "stage_index", "stage_minutes"] + FIELDS
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(stage_rows)

stats_rows = []
for f in FIELDS:
    vals = [r[f] for r in stage_rows if r.get(f) is not None]
    if not vals:
        continue
    stats_rows.append({
        "field": f,
        "n": len(vals),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "mean": round(statistics.fmean(vals), 4),
        "median": round(statistics.median(vals), 4),
        "std": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
    })

with open(os.path.join(_DIR, "stats_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["field", "n", "min", "max", "mean", "median", "std"])
    w.writeheader()
    w.writerows(stats_rows)

per_prompt_rows = []
prompts_seen = {}
for r in stage_rows:
    prompts_seen.setdefault(r["prompt_idx"], r["prompt"])
for p_idx in sorted(prompts_seen):
    for f in FIELDS:
        vals = [r[f] for r in stage_rows if r["prompt_idx"] == p_idx and r.get(f) is not None]
        if not vals:
            continue
        per_prompt_rows.append({
            "prompt_idx": p_idx,
            "prompt": prompts_seen[p_idx],
            "field": f,
            "n": len(vals),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
            "mean": round(statistics.fmean(vals), 4),
            "median": round(statistics.median(vals), 4),
            "std": round(statistics.pstdev(vals), 4) if len(vals) > 1 else 0.0,
        })

with open(os.path.join(_DIR, "per_prompt_stats.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["prompt_idx", "prompt", "field", "n", "min", "max", "mean", "median", "std"])
    w.writeheader()
    w.writerows(per_prompt_rows)

# 프롬프트별 stage_count/stage_minutes 변동성(참고) — 같은 프롬프트 3회 반복 시 구조 자체가
# 얼마나 안정적인지(단계 수 고정 여부, 구간 길이 편차).
meta_rows = []
for p_idx in sorted(prompts_seen):
    calls = [r for r in call_rows if r["prompt_idx"] == p_idx]
    stage_counts = [c["stage_count"] for c in calls if c["stage_count"] != ""]
    meta_rows.append({
        "prompt_idx": p_idx,
        "prompt": prompts_seen[p_idx],
        "n_calls": len(calls),
        "stage_counts": ",".join(str(c) for c in stage_counts),
        "stage_minutes_per_call": " | ".join(c["stage_minutes"] for c in calls if c["stage_minutes"]),
    })
with open(os.path.join(_DIR, "per_prompt_structure.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=["prompt_idx", "prompt", "n_calls", "stage_counts", "stage_minutes_per_call"])
    w.writeheader()
    w.writerows(meta_rows)

print("call_summary.csv rows:", len(call_rows))
print("stage_detail.csv rows:", len(stage_rows))
print("stats_summary.csv rows:", len(stats_rows))
print("per_prompt_stats.csv rows:", len(per_prompt_rows))
print("per_prompt_structure.csv rows:", len(meta_rows))
