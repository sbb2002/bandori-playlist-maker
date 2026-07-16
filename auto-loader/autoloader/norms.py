"""동결(frozen) 정규화 — 신곡을 기존 658곡과 같은 자로 재는 모듈.

songs_master.csv의 파생 컬럼 3계열은 모두 "전체 곡 분포" 기준 정규화 값이다.
신곡 반영 시 전체를 재계산하면 기존 658행이 전부 흔들리므로(diff 오염·재현성 상실),
형제 프로젝트 orchestrate.py의 "동결 norm" 선례를 따라 **원래 분포를 동결**하고
신곡만 그 분포에 대입한다. 기존 행은 바이트 불변.

동결 상수는 data/*.json으로 **영속화**한다 — 증분 append로 소스 CSV가 자라도
분포가 표류하지 않도록, 최초 1회 구축 시점의 값을 이후 실행이 그대로 재사용한다.

1) proxy z-score (energy/acousticness/instrumentalness_proxy) → data/feature_norms.json
   원본: 형제 genre_features_analyze.build_proxies — pandas zscore(ddof=1), 660곡 분포.
2) energy_full → data/energy_full_norm.json
   원본: build_energy_full.py — eligible 풀 robust z(med/MAD, GT 부호) →
   composite(mean5 + rms_p90×2, 부장 확정 2026-07-11) → eligible 백분위.
   ⚠️ 이 분포는 **중복 업로드 idx 525·588 제거(2026-07-13) 이전**(원시 660행,
   eligible 653곡) 기준이다 — master가 아니라 full_audio_features.csv 전체 +
   밴드 eligibility로 재구성해야 저장값이 재현된다(검증으로 확인).
3) i_* (시간분절 강도) → data/intensity_norm.json
   원본: extract_temporal_intensity.py — 전곡 프레임 피처의 전역 med/MAD z.
   전역 상수가 어디에도 저장돼 있지 않으므로 부트스트랩(기존 전곡 wav 1회 재산출)으로
   동결 상수를 만든다.
4) shape(재생 펄스 모양) → data/shape_norm.json
   원본: 형제 add_pulse_shape.py 채널 산식(z-score, ddof=0) 이식 — 형제 audio_map의
   신곡 엔트리에는 더 이상 shape가 없어(형식 변화, 2026-07-15 확인) 형제 값을 그대로
   못 쓴다. 우리 발췌 특징(excerpt_features.extract_from_wav)에 필요 원시 컬럼이
   전부 있으므로 형제 audio_map 의존 없이 직접 계산한다.

각 동결 분포는 기존 행 재계산 대조(verify_*)로 원본과의 일치를 검증한다.

외부 의존: numpy (+부트스트랩 시 librosa — extract_temporal_intensity 재사용).
"""
from __future__ import annotations

import bisect
import csv
import datetime
import json
import sys
from pathlib import Path

import numpy as np

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[1]
_DATA_SCRIPTS = _THIS_DIR.parent / "data"
if str(_DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DATA_SCRIPTS))

# 기존 모듈 재사용(재구현 금지): GT 라벨·프레임 피처 정의.
from build_energy_full import GT_LOUD, GT_QUIET  # noqa: E402
import extract_temporal_intensity as eti  # noqa: E402  (_frame_features, SR/HOP/SEG_SEC)

# ---------------------------------------------------------------------------
# 1) proxy z-score 동결
# ---------------------------------------------------------------------------

# genre_features_analyze.build_proxies가 소비하는 원시 컬럼.
PROXY_RAW_COLS = ["harmonic_ratio", "flatness", "voiced_frac_mix", "rms", "contrast", "flux"]


def build_proxy_norms(features_rows: list[dict]) -> dict[str, dict[str, float]]:
    """원시 컬럼별 mean/std(ddof=1 — pandas Series.std 기본값과 동일)."""
    norms: dict[str, dict[str, float]] = {}
    for col in PROXY_RAW_COLS:
        v = np.array([float(r[col]) for r in features_rows], dtype=np.float64)
        std = float(v.std(ddof=1))
        norms[col] = {"mean": float(v.mean()), "std": std or 1.0}
    return norms


def compute_proxies(raw: dict, norms: dict[str, dict[str, float]]) -> dict[str, float]:
    """genre_features_analyze.build_proxies 산식(동결 norm 대입)."""
    def z(col: str) -> float:
        n = norms[col]
        return (float(raw[col]) - n["mean"]) / n["std"]

    return {
        "acousticness_proxy": z("harmonic_ratio") - z("flatness"),
        "instrumentalness_proxy": -z("voiced_frac_mix"),
        "energy_proxy": z("rms") + z("contrast") + z("flux"),
    }


def verify_proxy_norms(features_rows: list[dict],
                       norms: dict[str, dict[str, float]]) -> float:
    """기존 행의 저장된 proxy를 동결 norm으로 재계산해 최대 절대오차 반환."""
    worst = 0.0
    for r in features_rows:
        got = compute_proxies(r, norms)
        for col, val in got.items():
            worst = max(worst, abs(val - float(r[col])))
    return worst


def load_or_build_proxy_norms(features_csv: Path, json_path: Path,
                              verify_tol: float = 1e-6) -> dict:
    """영속화된 동결 norm 로드. 없으면 현재 CSV 분포에서 구축·검증·저장."""
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))["norms"]
    with features_csv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    norms = build_proxy_norms(rows)
    worst = verify_proxy_norms(rows, norms)
    if worst > verify_tol:
        raise RuntimeError(
            f"proxy 동결 norm 재현 실패(max diff {worst:.3e} > {verify_tol}) — "
            "genre_features_analyze 산식/ddof 대조 필요")
    payload = {
        "purpose": "proxy z-score 동결 정규화 상수(신곡 증분용)",
        "source": "genre_features_analyze.build_proxies 재현 — "
                  "song_features_with_proxies.csv 원시 컬럼 mean/std(ddof=1)",
        "built_at": datetime.date.today().isoformat(),
        "n_rows": len(rows),
        "verify_max_abs_diff": worst,
        "norms": norms,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"proxy 동결 norm 저장: {json_path} (기존 {len(rows)}행 max diff {worst:.2e})")
    return norms


# ---------------------------------------------------------------------------
# 2) energy_full 동결 (composite + eligible 백분위)
# ---------------------------------------------------------------------------

# build_energy_full.main()의 FINAL 확정 레시피(부장 확정 2026-07-11) — 함수 내부
# 상수라 import 불가, 값 변경 시 그쪽과 함께 갱신할 것.
FINAL_FEATS = ["perc_mean", "onset_mean", "zcr_mean", "cen_mean", "flat_mean", "rms_p90"]
FINAL_W = [1.0, 1.0, 1.0, 1.0, 1.0, 2.0]


def latest_valid_feats(full_features_csv: Path) -> dict[int, dict]:
    """full_audio_features.csv에서 idx별 최신 정상 행(resume/재추출 안전 —
    build_energy_full._load_merged와 동일 규칙)."""
    feats: dict[int, dict] = {}
    with full_features_csv.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if (r.get("cen_mean") or "").strip() and not (r.get("error") or "").strip():
                feats[int(r["idx"])] = r
    return feats


class EnergyFullFrozen:
    """원래(2026-07-11) 분포에서 동결한 energy_full 계산기."""

    def __init__(self, norm: dict[str, dict[str, float]], pool_sorted: list[float]):
        self.norm = norm
        self._pool_sorted = pool_sorted

    # -- 구축/영속화 ---------------------------------------------------------

    @classmethod
    def build(cls, full_features_csv: Path,
              elig_by_band: dict[str, bool]) -> "EnergyFullFrozen":
        """원시 서브피처 CSV 전체(중복 업로드 idx 포함) + 밴드 eligibility로
        원래 분포를 재구성한다. master 기준이 아님에 주의(모듈 docstring §2)."""
        feats = latest_valid_feats(full_features_csv)
        if not feats:
            raise ValueError("full_audio_features.csv에서 유효 행이 없습니다.")
        merged = [{"idx": idx,
                   "elig": elig_by_band.get(r["band"], False),
                   "vals": {c: float(r[c]) for c in FINAL_FEATS}}
                  for idx, r in feats.items()]
        pool = [r for r in merged if r["elig"]]
        q_idx = {r["idx"] for r in merged} & set(GT_QUIET)
        l_idx = {r["idx"] for r in merged} & set(GT_LOUD)
        vals_by_idx = {r["idx"]: r["vals"] for r in merged}

        norm: dict[str, dict[str, float]] = {}
        for feat in FINAL_FEATS:
            vals = np.array([r["vals"][feat] for r in pool], dtype=np.float64)
            med = float(np.median(vals))
            mad = float(np.median(np.abs(vals - med)) * 1.4826)
            if mad < 1e-9:
                mad = float(vals.std()) + 1e-9
            zf = {i: (v[feat] - med) / mad for i, v in vals_by_idx.items()}
            qm = float(np.mean([zf[i] for i in sorted(q_idx)]))
            lm = float(np.mean([zf[i] for i in sorted(l_idx)]))
            norm[feat] = {"med": med, "mad": mad,
                          "orient": 1.0 if lm >= qm else -1.0}

        self = cls(norm, [])
        self._pool_sorted = sorted(self.composite(r["vals"]) for r in pool)
        return self

    @classmethod
    def load_or_build(cls, full_features_csv: Path, elig_by_band: dict[str, bool],
                      master_rows: list[dict], json_path: Path,
                      min_exact_ratio: float = 0.99) -> "EnergyFullFrozen":
        """영속화 로드. 없으면 구축 → 기존 master 저장값 재현 검증 → 저장."""
        if json_path.exists():
            d = json.loads(json_path.read_text(encoding="utf-8"))
            return cls(d["norm"], d["pool_sorted"])
        self = cls.build(full_features_csv, elig_by_band)
        ok, total, worst = self.verify(master_rows, full_features_csv)
        print(f"energy_full 동결 분포 검증: exact {ok}/{total}, max diff {worst:.2e}")
        if total == 0 or ok / total < min_exact_ratio:
            raise RuntimeError(
                "energy_full 분포 재현 실패 — build_energy_full.py와 대조 필요")
        payload = {
            "purpose": "energy_full 동결 분포(신곡 증분용)",
            "source": "build_energy_full.py FINAL(mean5+rms_p90x2) 재구성 — "
                      "원시 660행(중복 업로드 포함) eligible 풀",
            "built_at": datetime.date.today().isoformat(),
            "feats": FINAL_FEATS, "weights": FINAL_W,
            "verify": {"exact": ok, "total": total, "max_abs_diff": worst},
            "norm": self.norm,
            "pool_sorted": self._pool_sorted,
        }
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        print(f"energy_full 동결 분포 저장: {json_path} (풀 {len(self._pool_sorted)}곡)")
        return self

    # -- 계산 -----------------------------------------------------------------

    def _pct(self, v: float) -> float:
        """song_repo._percentile_ranker와 동일한 중앙순위 백분위."""
        srt = self._pool_sorted
        n = len(srt)
        if n == 0:
            return 0.5
        less = bisect.bisect_left(srt, v)
        equal = bisect.bisect_right(srt, v) - less
        return (less + 0.5 * equal) / n

    def composite(self, raw_vals: dict) -> float:
        return sum(w * ((float(raw_vals[f]) - self.norm[f]["med"]) / self.norm[f]["mad"]
                        * self.norm[f]["orient"])
                   for f, w in zip(FINAL_FEATS, FINAL_W)) / sum(FINAL_W)

    def energy_full_for(self, raw_vals: dict) -> float:
        """신곡 원시 서브피처 → 동결 분포 기준 energy_full(0~1)."""
        return self._pct(self.composite(raw_vals))

    def verify(self, master_rows: list[dict],
               full_features_csv: Path) -> tuple[int, int, float]:
        """기존 master 행 재계산 vs 저장값('%.6f'). (일치, 비교, 최대오차)."""
        feats = latest_valid_feats(full_features_csv)
        ok = total = 0
        worst = 0.0
        for m in master_rows:
            stored = (m.get("energy_full") or "").strip()
            idx = int(m["idx"])
            if not stored or idx not in feats:
                continue
            total += 1
            mine = self.energy_full_for(feats[idx])
            worst = max(worst, abs(mine - float(stored)))
            if f"{mine:.6f}" == stored:
                ok += 1
        return ok, total, worst


# ---------------------------------------------------------------------------
# 3) shape(재생 펄스 모양) 동결 — 형제 add_pulse_shape.py 산식 이식
# ---------------------------------------------------------------------------

# 형제 add_pulse_shape.py 채널 산식의 원시 컬럼. z-score는 ddof=0(형제 수식의
# 수동 population variance와 동일 — pandas/proxy 계열의 ddof=1과 다름에 주의).
SHAPE_RAW_COLS = ["harmonic_ratio", "centroid", "rolloff", "flatness", "flux", "zcr"]
SHAPE_BRIGHT_COLS = ("centroid", "rolloff", "zcr", "flatness")
SHAPE_NEUTRAL_GAP = 0.4


def build_shape_norms(features_rows: list[dict]) -> dict[str, dict[str, float]]:
    """원시 컬럼별 mean/std(ddof=0 — 형제 add_pulse_shape._zscore와 동일 산식)."""
    norms: dict[str, dict[str, float]] = {}
    for col in SHAPE_RAW_COLS:
        v = np.array([float(r[col]) for r in features_rows], dtype=np.float64)
        std = float(v.std(ddof=0))
        norms[col] = {"mean": float(v.mean()), "std": std or 1.0}
    return norms


def compute_shape(raw: dict, norms: dict[str, dict[str, float]]) -> str:
    """형제 add_pulse_shape.py 채널 산식(동결 norm 대입) — neutral/acoustic/bright/shimmer."""
    def z(col: str) -> float:
        n = norms[col]
        return (float(raw[col]) - n["mean"]) / n["std"]

    acoustic = z("harmonic_ratio")
    bright = sum(z(c) for c in SHAPE_BRIGHT_COLS) / len(SHAPE_BRIGHT_COLS)
    shimmer = z("flux")
    ranked = sorted([("acoustic", acoustic), ("bright", bright), ("shimmer", shimmer)],
                    key=lambda kv: kv[1], reverse=True)
    top_name, top_val = ranked[0]
    _, second_val = ranked[1]
    return top_name if (top_val - second_val) >= SHAPE_NEUTRAL_GAP else "neutral"


def verify_shape_norms(features_rows: list[dict], norms: dict[str, dict[str, float]],
                       stored_shape_by_idx: dict[int, str]) -> tuple[int, int]:
    """기존 곡(idx 매칭)의 저장된 shape 재계산 대조.
    (일치, 비교) 반환 — 저장된 shape 없는 행은 건너뛴다.

    대조군은 songs_master.csv의 이미 계산된 shape 컬럼이다(2026-07-16 변경 — 원래
    형제 audio_map.json의 songs[] 배열 shape 필드를 대조군으로 썼으나, 형제 쪽에서
    그 필드가 전곡(기존 곡 포함) 소실돼 대조 불가능해짐. master.csv는 그 값이 과거에
    이미 계산·저장돼 있어 여전히 유효한 대조군이다)."""
    ok = total = 0
    for r in features_rows:
        idx = int(r["idx"])
        stored = stored_shape_by_idx.get(idx)
        if not stored:
            continue
        total += 1
        if compute_shape(r, norms) == stored:
            ok += 1
    return ok, total


def load_or_build_shape_norms(features_csv: Path, master_rows: list[dict], json_path: Path,
                              min_exact_ratio: float = 0.99) -> dict:
    """영속화된 동결 shape norm 로드. 없으면 현재 분포에서 구축·검증·저장.

    검증 대조군은 songs_master.csv(호출측이 이미 로드해 전달하는 master_rows)의
    shape 컬럼이다 — verify_shape_norms 문서 참조."""
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))["norms"]
    with features_csv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    norms = build_shape_norms(rows)
    stored_by_idx = {int(r["idx"]): r.get("shape", "") for r in master_rows}
    ok, total = verify_shape_norms(rows, norms, stored_by_idx)
    if total == 0 or ok / total < min_exact_ratio:
        raise RuntimeError(
            f"shape 동결 norm 재현 실패({ok}/{total}) — "
            "형제 add_pulse_shape.py 산식/ddof 대조 필요")
    payload = {
        "purpose": "재생 펄스 shape 동결 정규화 상수(신곡 증분용, 형제 audio_map "
                  "shape 필드 소실 대응)",
        "source": "형제 add_pulse_shape.py 채널 산식 이식 — "
                  "song_features_with_proxies.csv 원시 컬럼 mean/std(ddof=0). "
                  "검증 대조군은 songs_master.csv의 기존 shape 컬럼(형제 audio_map은 "
                  "shape 필드 소실로 대조 불가, 2026-07-16 확인).",
        "built_at": datetime.date.today().isoformat(),
        "n_rows": len(rows),
        "verify": {"exact": ok, "total": total},
        "norms": norms,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    print(f"shape 동결 norm 저장: {json_path} (기존 {total}행 exact {ok})")
    return norms


# ---------------------------------------------------------------------------
# 4) i_* (시간분절 강도) 동결 — 부트스트랩 + 적용
# ---------------------------------------------------------------------------

_SEG_FRAMES = int(eti.SEG_SEC * eti.SR / eti.HOP)
I_FIELDS = ["i_mean", "i_std", "i_max", "i_min", "i_start", "i_end"]


def _frames_worker(task: tuple[int, str]) -> tuple[int, np.ndarray | None, str]:
    """멀티프로세싱 worker: wav → (n,6) float32 프레임 피처.
    extract_temporal_intensity._frame_features를 그대로 재사용한다."""
    idx, path = task
    try:
        import librosa
        y, _ = librosa.load(path, sr=eti.SR, mono=True)
        return idx, eti._frame_features(y).astype(np.float32), ""
    except Exception as exc:  # noqa: BLE001 — 곡별 격리
        return idx, None, repr(exc)


def compute_frames_for(path: Path) -> np.ndarray:
    """단일 wav의 프레임 피처(신곡 처리용)."""
    _idx, frames, err = _frames_worker((0, str(path)))
    if frames is None:
        raise RuntimeError(f"프레임 피처 실패: {path.name} — {err}")
    return frames


def aggregate_intensity(frames: np.ndarray, med: np.ndarray, mad: np.ndarray) -> dict[str, str]:
    """extract_temporal_intensity.main의 집계부 산식 그대로('%.5f' 문자열)."""
    z = (frames - med) / mad
    inten = z.mean(axis=1)
    s = inten[:_SEG_FRAMES] if len(inten) > _SEG_FRAMES else inten
    e = inten[-_SEG_FRAMES:] if len(inten) > _SEG_FRAMES else inten
    return {
        "i_mean": f"{inten.mean():.5f}", "i_std": f"{inten.std():.5f}",
        "i_max": f"{np.percentile(inten, 95):.5f}",
        "i_min": f"{np.percentile(inten, 5):.5f}",
        "i_start": f"{s.mean():.5f}", "i_end": f"{e.mean():.5f}",
    }


def bootstrap_intensity_norm(basis_rows: list[dict], audio_dir: Path,
                             out_json: Path, workers: int = 6) -> dict:
    """기존 전곡 wav에서 전역 med/MAD를 1회 재산출해 동결 저장.

    basis_rows: **원본 추출과 동일한 곡 세트**여야 한다 — temporal_intensity.csv의
    660행(중복 업로드 idx 525·588 포함). master(658행) 기준으로 돌리면 분포가 살짝
    어긋나 기존 i_*가 재현되지 않는다(실측: max diff 6.4e-3 → 660곡 기준 필요).
    행에 저장된 i_*가 있으면 검증에 사용한다.

    extract_temporal_intensity.main의 전역 정규화 코드를 그대로 따른다(float32).
    반환 dict에 검증 결과(기존 i_*와의 일치율)를 포함한다.
    """
    tasks = []
    for r in basis_rows:
        p = audio_dir / f"{r['band']}__{int(r['idx']):03d}.wav"
        if p.exists():
            tasks.append((int(r["idx"]), str(p)))
        else:
            print(f"  [skip] {p.name} 없음", flush=True)

    print(f"부트스트랩: {len(tasks)}곡 프레임 피처 산출(workers={workers})…", flush=True)
    per_song: dict[int, np.ndarray] = {}
    if workers <= 1:
        results = map(_frames_worker, tasks)
        pool = None
    else:
        import multiprocessing as mp
        pool = mp.Pool(processes=workers)
        results = pool.imap_unordered(_frames_worker, tasks)
    n = 0
    for idx, frames, err in results:
        n += 1
        if frames is None:
            print(f"  [err] idx={idx}: {err}", flush=True)
        else:
            per_song[idx] = frames
        if n % 50 == 0:
            print(f"  {n}/{len(tasks)}", flush=True)
    if pool is not None:
        pool.close()
        pool.join()

    # --- 전역 robust 정규화(원본 코드 그대로) ---
    allframes = np.concatenate(list(per_song.values()), axis=0)
    med = np.median(allframes, axis=0)
    mad = np.median(np.abs(allframes - med), axis=0) * 1.4826
    mad[mad < 1e-9] = allframes.std(axis=0)[mad < 1e-9] + 1e-9

    # --- 검증: 기반 행의 저장된 i_*를 재계산해 대조 ---
    by_idx = {int(r["idx"]): r for r in basis_rows}
    ok = total = 0
    worst = 0.0
    for idx, frames in per_song.items():
        stored_row = by_idx.get(idx)
        if not stored_row or not (stored_row.get("i_mean") or "").strip():
            continue
        mine = aggregate_intensity(frames, med, mad)
        for f in I_FIELDS:
            total += 1
            stored = (stored_row.get(f) or "").strip()
            worst = max(worst, abs(float(mine[f]) - float(stored)))
            if mine[f] == stored:
                ok += 1

    payload = {
        "purpose": "i_* 시간분절 강도의 전역 동결 정규화 상수(신곡 증분용)",
        "source": "extract_temporal_intensity.py 산식 재현 — 기존 전곡 wav 부트스트랩",
        "built_at": datetime.date.today().isoformat(),
        "n_songs": len(per_song),
        "sr": eti.SR, "hop": eti.HOP, "seg_sec": eti.SEG_SEC,
        "feats": list(eti.FEATS),
        "med": [float(x) for x in med],
        "mad": [float(x) for x in mad],
        "verify": {"exact": ok, "total": total, "max_abs_diff": worst},
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"동결 상수 저장: {out_json}  (검증 exact {ok}/{total}, max diff {worst:.2e})",
          flush=True)
    return payload


def load_intensity_norm(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """저장된 동결 상수 로드 → (med, mad) float32(원본 파이프라인 dtype)."""
    d = json.loads(path.read_text(encoding="utf-8"))
    return (np.array(d["med"], dtype=np.float32),
            np.array(d["mad"], dtype=np.float32))


def band_average_intensity(master_rows: list[dict], band: str,
                           exclude_idx: frozenset[int] = frozenset()) -> dict[str, str] | None:
    """i_* 동결 상수가 없는 환경(soft-run)의 임시 대체값 — 같은 밴드 기존 곡의
    i_* 평균('%.5f', aggregate_intensity와 동일 포맷). provisional 행 자체는
    자기 자신을 평균에 오염시키지 않도록 exclude_idx로 제외한다.
    같은 밴드에 참조할 실측 행이 하나도 없으면 None(호출측이 스킵 여부 판단)."""
    vals: dict[str, list[float]] = {f: [] for f in I_FIELDS}
    for r in master_rows:
        if r["band"] != band or int(r["idx"]) in exclude_idx:
            continue
        if not all((r.get(f) or "").strip() for f in I_FIELDS):
            continue
        for f in I_FIELDS:
            vals[f].append(float(r[f]))
    if not vals["i_mean"]:
        return None
    return {f: f"{np.mean(vals[f]):.5f}" for f in I_FIELDS}
