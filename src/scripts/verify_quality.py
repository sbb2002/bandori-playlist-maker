#!/usr/bin/env python3
"""setlist-maker 플레이리스트 품질 측정 하네스 (정형 검증 방법론).

목적
----
현재까지 무드 매칭 검증은 "특정 곡을 눈으로 확인"하는 임시방편이었다. 이 하네스는
**고정 시나리오 셋 × 정형 지표 × 그라운드트루스**로 플레이리스트 품질을 **반복·재현 가능하게**
측정한다. 앞으로의 모든 엔진 변경을 이 고정 기준으로 before/after 비교할 수 있다.

무엇을 하는가
-------------
1. 고정 시나리오(대표 요청 12종, MoodParameters 고정 → LLM 없이 재현 가능)를 현재 엔진
   (`build_setlist`)에 태운다.
2. 시드 고정 다중 실행(기본 20회)으로 각 지표를 평균±표준편차로 안정화한다(Stage A/B의 rng 변주 흡수).
3. 세트리스트당 지표(전부 순수 함수, CSV/엔진 출력 기반)를 계산해 스코어카드를 출력한다.
4. 시나리오별 pass/fail 게이트를 평가한다(임계값은 document-archive 브랜치 archive/research/2026-07-11-verification-methodology.md).

지표(요약)
----------
- mood_leak_rate     : 곡 강도가 소속 단계 목표에서 LEAK_TOL 초과로 벗어난 곡 비율(무드 누출).
- gt_loud_in_setlist : 그라운드트루스 '시끄러움' 곡의 등장 수(조용 요청에서 0이어야 함).
- max_intensity / mean_intensity : 세트리스트 강도 최댓/평균값.
- boundary_gap_mean/max : 이전 곡 아웃트로 텐션 ↔ 다음 곡 인트로 텐션 |차이|(경계 연속성). 낮을수록 좋음.
- bright_swing_mean/max : 인접 곡 밝기 |차이|(밝기 급반전). 낮을수록 좋음.
- opener_intro       : 첫 곡 인트로 텐션(오프너가 조용하게 시작하는지). 파티/운동은 높아야.
- harmonic_rate      : 인접 전환 중 하모닉 호환(동일/인접 조성) 비율. 높을수록 좋음.
- arc_target_mae     : 단계별 실제 평균강도 vs 단계 목표의 평균 |오차|. 낮을수록 목표 정합.
- arc_dir_consistency: 단계 간 강도 변화가 요청 아크 방향과 일치하는 비율(상승/하강/평탄).
- coh_energy / coh_brightness / coh_tonality : EPJ 다양성정규화 응집성(§1.2), 범위 [-1,1]. 높을수록 매끄러움.
- mean_brightness    : 세트리스트 평균 밝기(어두움 요청은 낮게, 밝음 요청은 높게).
- gt_party_frac      : 그라운드트루스 '파티' 앵커 곡 비율(파티/클럽 요청 참고 — 장르 피처 부재로 강도 근사).

실행
----
    python src/scripts/verify_quality.py                 # 전 시나리오 스코어카드 + pass/fail
    python src/scripts/verify_quality.py --seeds 50      # 시드 50회 평균(정밀)
    python src/scripts/verify_quality.py --scenario quiet_calm   # 특정 시나리오만
    python src/scripts/verify_quality.py --markdown      # 보고서용 마크다운 표 출력
    python src/scripts/verify_quality.py --csv out.csv   # 원자료 CSV 저장

재현성: 시드 리스트는 고정(0..seeds-1). 동일 입력·동일 CSV → 동일 출력.
경로 권한(R6/R11): 이 파일은 src/scripts/ (쓰기 허용). 엔진은 import해 호출만(수정 없음).
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── 엔진 import (읽기 전용 호출) ──────────────────────────────────────────────
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parents[2]                    # .../bandori-playlist-maker
_BACKEND = _REPO_ROOT / "src" / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.domain.harmonic import is_compatible          # noqa: E402
from app.domain.models import MoodParameters           # noqa: E402
from app.domain.selection import _brightness_scores, build_setlist  # noqa: E402
from app.repo.song_repo import load_songs              # noqa: E402

_GT_CSV = _REPO_ROOT / "data" / "ground_truth_labels.csv"

# 무드 누출 판정 창(엔진 선곡 tol=0.08보다 넉넉 — "명백한" 누출만 잡음).
LEAK_TOL = 0.20
# 평탄(flat) 아크에서 "단계 변화 없음"으로 인정하는 |단계간 강도차| 상한.
FLAT_STEP = 0.08


# ── 그라운드트루스 ────────────────────────────────────────────────────────────
def load_ground_truth() -> dict[tuple[str, str], set[int]]:
    """data/ground_truth_labels.csv → {(dimension, label): {idx,...}}.

    라벨은 곡 정체성 기반의 방향성 근거(소규모·수작업, 통계 유의성 주장 아님).
    dimension ∈ {intensity, brightness, party}, label ∈ {quiet/loud, bright/dark, party/calm}.
    """
    gt: dict[tuple[str, str], set[int]] = {}
    with _GT_CSV.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            gt.setdefault((r["dimension"], r["label"]), set()).add(int(r["idx"]))
    return gt


# ── 조성(camelot) → EPJ 3D 임베딩 (§1.2 / 보고서 부록 A) ─────────────────────
_H = 2.0 * math.sin(math.pi / 12.0)  # ≈ 0.5176 (장조 바닥 z=0, 단조 위 z=h)


def tonality_xyz(camelot: str) -> tuple[float, float, float]:
    """camelot 'nL'(n=1..12, L∈{A=단조, B=장조}) → 5도권 12각기둥 3D 좌표.

    θ = 2π(n−1)/12, (cosθ, sinθ, z); z = 0 if 장조(B) else h. 유클리드 거리로 조성 근접 측정.
    """
    n = int(camelot[:-1])
    letter = camelot[-1]
    theta = 2.0 * math.pi * (n - 1) / 12.0
    z = 0.0 if letter == "B" else _H
    return (math.cos(theta), math.sin(theta), z)


def _euclid(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


# ── EPJ 응집성(coherence) (§1.2, 보고서 부록 A) ──────────────────────────────
def coherence(points: list, dist) -> float:
    """coh = 1 − (n/2)·Σ d(x_i,x_{i+1})² / Σ_{i<j} d(x_i,x_j)², 범위 [−1,1].

    다양성(전체 쌍거리)으로 인접 변화량을 정규화한 순서의존 응집성. 높을수록 매끄러움.
    n<2 또는 전체 다양성 0(모든 곡 동일)일 때는 정의 불가 → 0.0(중립) 반환.
    """
    n = len(points)
    if n < 2:
        return 0.0
    seq_sq = sum(dist(points[i], points[i + 1]) ** 2 for i in range(n - 1))
    all_sq = sum(dist(points[i], points[j]) ** 2 for i in range(n) for j in range(i + 1, n))
    if all_sq <= 1e-12:
        return 0.0
    return 1.0 - (n / 2.0) * seq_sq / all_sq


# ── 곡 피처 룩업(엔진과 동일 산출) ──────────────────────────────────────────
class Features:
    """idx → (intensity, brightness, intro, outro, camelot). 엔진과 동일 근거로 산출.

    intensity  = Song.energy (song_repo의 다신호 soft-OR 강도, 0~1).
    brightness = selection._brightness_scores (eligible 풀 기준, -1~1). 엔진이 최적화하는 값 그대로.
    intro/outro = Song.intro_energy(i_start) / outro_energy(i_end) — 곡 경계 텐션.
    """

    def __init__(self, songs: list) -> None:
        elig = [s for s in songs if s.eligible_band]
        self.brightness = _brightness_scores(elig)
        self.intensity = {s.idx: s.energy for s in elig}
        self.intro = {s.idx: s.intro_energy for s in elig}
        self.outro = {s.idx: s.outro_energy for s in elig}
        self.camelot = {s.idx: s.camelot for s in elig}


# ── 시나리오 정의 ────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Scenario:
    """고정 시나리오 1건. params 고정(LLM 없이 재현) + 기대 속성(pass/fail 게이트)."""

    id: str
    name: str                    # 대표 자연어 요청(사람이 읽는 라벨)
    profile: str                 # quiet | rising | descending | flat | party | dark | bright
    brightness: float
    start_energy: float
    end_energy: float
    stage_count: int
    target_minutes: int
    gates: dict = field(default_factory=dict)   # {metric: (op, threshold)} op ∈ {"<=",">=","=="}

    def to_params(self) -> MoodParameters:
        return MoodParameters(
            brightness=self.brightness,
            start_energy=self.start_energy,
            end_energy=self.end_energy,
            stage_count=self.stage_count,
            target_minutes=self.target_minutes,
        )


# 게이트 임계값 근거: document-archive 브랜치 archive/research/2026-07-11-verification-methodology.md §4.
# 공통 게이트(전 시나리오): 경계 연속성·하모닉·밝기 급변.
_COMMON_GATES = {
    "boundary_gap_mean": ("<=", 0.30),   # 평균 경계 갭 ≈ 0.5·std(intro/outro). 셔플 0.52·랜덤 0.70 대비.
    "boundary_gap_max": ("<=", 1.50),    # 단일 급전(사용자가 실제로 체감하는 "튀는 전환") 상한.
    "harmonic_rate": (">=", 0.35),       # 풀 랜덤 하모닉율 0.19의 약 2배 = 현실적 하한(0.50은 연속성과 상충).
    "bright_swing_mean": ("<=", 0.60),
}


def _gates(**extra) -> dict:
    g = dict(_COMMON_GATES)
    g.update(extra)
    return g


SCENARIOS: list[Scenario] = [
    Scenario("quiet_calm", "조용하고 잔잔한 1시간", "quiet",
             brightness=0.1, start_energy=0.12, end_energy=0.12, stage_count=3, target_minutes=60,
             gates=_gates(max_intensity=("<=", 0.30), gt_loud_in_setlist=("==", 0),
                          mean_intensity=("<=", 0.25), arc_target_mae=("<=", 0.12))),
    Scenario("focus_study", "차분하게 집중·공부 30분", "quiet",
             brightness=0.0, start_energy=0.15, end_energy=0.15, stage_count=2, target_minutes=30,
             gates=_gates(max_intensity=("<=", 0.32), gt_loud_in_setlist=("==", 0),
                          mean_intensity=("<=", 0.28))),
    Scenario("emotional_ballad", "감성적이고 애절한 발라드 40분", "quiet",
             brightness=-0.3, start_energy=0.25, end_energy=0.20, stage_count=2, target_minutes=40,
             gates=_gates(max_intensity=("<=", 0.45), mean_brightness=("<=", 0.10))),
    Scenario("rising_feelgood", "기분 좋아지는 점점 고조되는 1시간", "rising",
             brightness=0.6, start_energy=0.35, end_energy=0.85, stage_count=3, target_minutes=60,
             gates=_gates(arc_dir_consistency=(">=", 0.99), arc_target_mae=("<=", 0.15),
                          opener_intro=(">=", -0.20))),
    Scenario("gentle_morning", "잔잔히 시작해 서서히 깨어나는 아침 45분", "rising",
             brightness=0.4, start_energy=0.20, end_energy=0.55, stage_count=3, target_minutes=45,
             gates=_gates(arc_dir_consistency=(">=", 0.99), arc_target_mae=("<=", 0.15))),
    Scenario("workout_burn", "운동·유산소로 불태울 45분", "rising",
             brightness=0.3, start_energy=0.65, end_energy=0.90, stage_count=3, target_minutes=45,
             gates=_gates(arc_dir_consistency=(">=", 0.99), mean_intensity=(">=", 0.60),
                          opener_intro=(">=", 0.20))),
    Scenario("party_hype", "신나는 파티 45분", "party",
             brightness=0.5, start_energy=0.80, end_energy=0.85, stage_count=3, target_minutes=45,
             gates=_gates(mean_intensity=(">=", 0.65), opener_intro=(">=", 0.30))),
    Scenario("club_music", "클럽 음악 45분", "party",
             brightness=0.2, start_energy=0.75, end_energy=0.80, stage_count=3, target_minutes=45,
             gates=_gates(mean_intensity=(">=", 0.60), opener_intro=(">=", 0.20))),
    Scenario("dark_intense", "어둡고 강렬한 45분", "dark",
             brightness=-0.6, start_energy=0.60, end_energy=0.70, stage_count=3, target_minutes=45,
             gates=_gates(mean_brightness=("<=", -0.20), mean_intensity=(">=", 0.50))),
    Scenario("bright_pop", "밝고 통통 튀는 팝 45분", "bright",
             brightness=0.8, start_energy=0.50, end_energy=0.60, stage_count=3, target_minutes=45,
             gates=_gates(mean_brightness=(">=", 0.30))),
    Scenario("wind_down", "하루 마무리, 점점 차분해지는 1시간", "descending",
             brightness=-0.1, start_energy=0.60, end_energy=0.20, stage_count=3, target_minutes=60,
             gates=_gates(arc_dir_consistency=(">=", 0.99), arc_target_mae=("<=", 0.15))),
    Scenario("steady_drive", "드라이브용 적당히 신나는 일정한 1시간", "flat",
             brightness=0.3, start_energy=0.55, end_energy=0.55, stage_count=3, target_minutes=60,
             gates=_gates(arc_target_mae=("<=", 0.12))),
]


# ── 지표 계산 (세트리스트 1건) ───────────────────────────────────────────────
def compute_metrics(setlist, feats: Features, gt: dict, scenario: Scenario) -> dict:
    """세트리스트 1건에 대한 전 지표 dict. 전부 순수 함수(엔진/CSV 파생값만 사용)."""
    picks = setlist.picks
    idxs = [p.idx for p in picks]
    n = len(picks)
    inten = [p.energy for p in picks]                       # 강도(엔진 출력)
    bright = [feats.brightness[i] for i in idxs]
    intro = [feats.intro[i] for i in idxs]
    outro = [feats.outro[i] for i in idxs]
    cam = [p.camelot for p in picks]

    m: dict[str, float] = {"n_songs": float(n)}

    # 무드 누출: 곡 강도가 소속 단계 목표에서 LEAK_TOL 초과로 벗어난 비율.
    stage_target = {st.index: st.energy_target for st in setlist.stages}
    leaks = sum(1 for p in picks if abs(p.energy - stage_target[p.stage_index]) > LEAK_TOL)
    m["mood_leak_rate"] = leaks / n if n else 0.0
    m["max_intensity"] = max(inten) if inten else 0.0
    m["mean_intensity"] = statistics.fmean(inten) if inten else 0.0

    # 그라운드트루스 누출/파티(방향성 근거).
    loud_gt = gt.get(("intensity", "loud"), set())
    party_gt = gt.get(("party", "party"), set())
    m["gt_loud_in_setlist"] = float(sum(1 for i in idxs if i in loud_gt))
    m["gt_party_frac"] = (sum(1 for i in idxs if i in party_gt) / n) if n else 0.0

    # 경계 텐션 연속성: |이전 아웃트로 − 다음 인트로|.
    gaps = [abs(outro[i] - intro[i + 1]) for i in range(n - 1)]
    m["boundary_gap_mean"] = statistics.fmean(gaps) if gaps else 0.0
    m["boundary_gap_max"] = max(gaps) if gaps else 0.0

    # 인접 밝기 급변: |밝기 차|.
    bswing = [abs(bright[i] - bright[i + 1]) for i in range(n - 1)]
    m["bright_swing_mean"] = statistics.fmean(bswing) if bswing else 0.0
    m["bright_swing_max"] = max(bswing) if bswing else 0.0

    # 오프너 인트로 텐션(첫 곡).
    m["opener_intro"] = intro[0] if intro else 0.0

    # 하모닉 전환율: 인접 쌍 중 동일/인접 조성 비율.
    if n >= 2:
        compat = sum(1 for i in range(n - 1) if cam[i] == cam[i + 1] or is_compatible(cam[i], cam[i + 1]))
        m["harmonic_rate"] = compat / (n - 1)
    else:
        m["harmonic_rate"] = 0.0

    # 아크: 단계별 실제 평균강도 vs 목표, 그리고 단계 간 방향 일치.
    stage_inten: dict[int, list[float]] = {}
    for p in picks:
        stage_inten.setdefault(p.stage_index, []).append(p.energy)
    stage_ids = sorted(stage_inten)
    stage_means = [statistics.fmean(stage_inten[k]) for k in stage_ids]
    targets = [stage_target[k] for k in stage_ids]
    m["arc_target_mae"] = statistics.fmean(abs(sm - t) for sm, t in zip(stage_means, targets)) if stage_means else 0.0
    exp_dir = _sign(scenario.end_energy - scenario.start_energy)
    if len(stage_means) >= 2:
        ok = 0
        for a, b in zip(stage_means, stage_means[1:]):
            step = b - a
            if exp_dir == 0:
                ok += 1 if abs(step) <= FLAT_STEP else 0
            else:
                ok += 1 if _sign(step) == exp_dir else 0
        m["arc_dir_consistency"] = ok / (len(stage_means) - 1)
    else:
        m["arc_dir_consistency"] = 1.0

    # EPJ 응집성(에너지·밝기·조성).
    m["coh_energy"] = coherence(inten, lambda x, y: abs(x - y))
    m["coh_brightness"] = coherence(bright, lambda x, y: abs(x - y))
    m["coh_tonality"] = coherence([tonality_xyz(c) for c in cam], _euclid)

    m["mean_brightness"] = statistics.fmean(bright) if bright else 0.0
    return m


def _sign(x: float) -> int:
    return (x > 1e-9) - (x < -1e-9)


# ── 시나리오 실행(시드 다중 평균) ───────────────────────────────────────────
# 스코어카드에 표시할 지표 순서.
METRIC_ORDER = [
    "mood_leak_rate", "gt_loud_in_setlist", "max_intensity", "mean_intensity",
    "boundary_gap_mean", "boundary_gap_max", "bright_swing_mean", "opener_intro",
    "harmonic_rate", "arc_target_mae", "arc_dir_consistency",
    "coh_energy", "coh_brightness", "coh_tonality", "mean_brightness", "gt_party_frac",
]


def run_scenario(songs, feats, gt, scenario: Scenario, seeds: list[int]) -> dict:
    """시드별 세트리스트 지표를 평균±표준편차로 집계."""
    per_seed: list[dict] = []
    target_seconds = scenario.target_minutes * 60
    for s in seeds:
        setlist = build_setlist(songs, scenario.to_params(), target_seconds, rng=random.Random(s))
        per_seed.append(compute_metrics(setlist, feats, gt, scenario))
    keys = per_seed[0].keys()
    mean = {k: statistics.fmean(d[k] for d in per_seed) for k in keys}
    std = {k: (statistics.pstdev(d[k] for d in per_seed) if len(per_seed) > 1 else 0.0) for k in keys}
    return {"mean": mean, "std": std, "n_seeds": len(seeds)}


def evaluate_gates(mean: dict, gates: dict) -> list[tuple[str, str, float, float, bool]]:
    """게이트 평가 → [(metric, op, threshold, value, passed)]."""
    out = []
    for metric, (op, thr) in gates.items():
        v = mean.get(metric, float("nan"))
        if op == "<=":
            ok = v <= thr + 1e-9
        elif op == ">=":
            ok = v >= thr - 1e-9
        else:  # "=="
            ok = abs(v - thr) < 0.5  # 카운트 지표(정수) 허용
        out.append((metric, op, thr, v, ok))
    return out


# ── 출력 ─────────────────────────────────────────────────────────────────────
def _fmt(v: float) -> str:
    return f"{v:.3f}"


def print_scorecard(results: dict) -> None:
    print("\n" + "=" * 78)
    print("스코어카드 — 현재 엔진 베이스라인 (시드 평균)")
    print("=" * 78)
    for sc in SCENARIOS:
        if sc.id not in results:
            continue
        r = results[sc.id]
        mean, std = r["mean"], r["std"]
        print(f"\n■ {sc.id}  [{sc.profile}]  \"{sc.name}\"  "
              f"(b={sc.brightness:+.2f} E:{sc.start_energy:.2f}→{sc.end_energy:.2f} "
              f"N={sc.stage_count} {sc.target_minutes}m, seeds={r['n_seeds']})")
        for k in METRIC_ORDER:
            print(f"    {k:<22} {mean[k]:>8.3f}  ±{std[k]:.3f}")
        gate_rows = evaluate_gates(mean, sc.gates)
        n_pass = sum(1 for *_, ok in gate_rows if ok)
        print(f"    ── 게이트 {n_pass}/{len(gate_rows)} 통과 ──")
        for metric, op, thr, v, ok in gate_rows:
            mark = "PASS" if ok else "FAIL"
            print(f"       [{mark}] {metric} {op} {thr}  (실측 {_fmt(v)})")


def print_markdown(results: dict) -> None:
    """보고서용 마크다운 표(시나리오 × 핵심 지표)."""
    cols = ["mood_leak_rate", "gt_loud_in_setlist", "max_intensity", "mean_intensity",
            "boundary_gap_mean", "bright_swing_mean", "opener_intro", "harmonic_rate",
            "arc_target_mae", "arc_dir_consistency", "coh_energy", "coh_tonality", "mean_brightness"]
    short = {"mood_leak_rate": "leak", "gt_loud_in_setlist": "gtLoud", "max_intensity": "maxI",
             "mean_intensity": "meanI", "boundary_gap_mean": "bGap", "bright_swing_mean": "bSwing",
             "opener_intro": "opnIntro", "harmonic_rate": "harm", "arc_target_mae": "arcMAE",
             "arc_dir_consistency": "arcDir", "coh_energy": "cohE", "coh_tonality": "cohT",
             "mean_brightness": "meanB"}
    print("\n" + "#" * 3 + " 마크다운 표 (복사용)\n")
    header = "| scenario | profile | " + " | ".join(short[c] for c in cols) + " |"
    sep = "|" + "---|" * (len(cols) + 2)
    print(header)
    print(sep)
    for sc in SCENARIOS:
        if sc.id not in results:
            continue
        mean = results[sc.id]["mean"]
        cells = " | ".join(f"{mean[c]:.3f}" for c in cols)
        print(f"| {sc.id} | {sc.profile} | {cells} |")


def print_gate_summary(results: dict) -> None:
    print("\n" + "=" * 78)
    print("게이트 요약 (pass/fail)")
    print("=" * 78)
    total_pass = total = 0
    for sc in SCENARIOS:
        if sc.id not in results:
            continue
        rows = evaluate_gates(results[sc.id]["mean"], sc.gates)
        np_ = sum(1 for *_, ok in rows if ok)
        total_pass += np_
        total += len(rows)
        fails = [r[0] for r in rows if not r[4]]
        status = "OK" if np_ == len(rows) else "취약: " + ", ".join(fails)
        print(f"  {sc.id:<18} {np_}/{len(rows)}  {status}")
    print(f"\n  전체 게이트: {total_pass}/{total} 통과")


def write_csv(results: dict, path: Path) -> None:
    cols = ["scenario", "profile", "n_seeds", "stat"] + METRIC_ORDER
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for sc in SCENARIOS:
            if sc.id not in results:
                continue
            r = results[sc.id]
            for stat in ("mean", "std"):
                row = {"scenario": sc.id, "profile": sc.profile, "n_seeds": r["n_seeds"], "stat": stat}
                row.update({k: f"{r[stat][k]:.5f}" for k in METRIC_ORDER})
                w.writerow(row)
    print(f"\n[CSV] 원자료 저장: {path}")


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    ap = argparse.ArgumentParser(description="setlist-maker 품질 측정 하네스")
    ap.add_argument("--seeds", type=int, default=20, help="시드 다중 실행 횟수(기본 20)")
    ap.add_argument("--scenario", default=None, help="특정 시나리오 id만 실행")
    ap.add_argument("--markdown", action="store_true", help="보고서용 마크다운 표도 출력")
    ap.add_argument("--csv", default=None, help="원자료 CSV 저장 경로")
    args = ap.parse_args()

    songs = load_songs()
    feats = Features(songs)
    gt = load_ground_truth()
    seeds = list(range(args.seeds))

    scenarios = SCENARIOS
    if args.scenario:
        scenarios = [s for s in SCENARIOS if s.id == args.scenario]
        if not scenarios:
            print(f"알 수 없는 시나리오: {args.scenario}")
            print("사용 가능:", ", ".join(s.id for s in SCENARIOS))
            return

    results = {sc.id: run_scenario(songs, feats, gt, sc, seeds) for sc in scenarios}

    n_elig = sum(1 for s in songs if s.eligible_band)
    print(f"곡 로드: {len(songs)} (eligible {n_elig}) · 시나리오 {len(results)} · 시드 {len(seeds)}회 평균")
    print_scorecard(results)
    print_gate_summary(results)
    if args.markdown:
        print_markdown(results)
    if args.csv:
        write_csv(results, Path(args.csv))


if __name__ == "__main__":
    main()
