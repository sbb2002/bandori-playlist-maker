"""bpm_madmom을 Bestdori 공식 BPM과 대조해 옥타브(반절/배속) 오차를 찾는다.

참조 파일: topic/20260720_audio_feats_analysis/out/bestdori_bpm.csv
(이전 세션에 Bestdori에서 크롤링한 공식 BPM. idx 기준 조인 — 커버곡 등 일부는 매칭 없음)

산출물:
- out/tempo_bestdori_comparison.csv : idx별 madmom vs official_bpm 전체 비교
- out/tempo_bestdori_mismatch.md    : |ratio-1| > 8% 곡 목록(옥타브 오차 후보)
- out/tempo_bestdori_scatter.png    : madmom vs official 산점도(대각선 + 0.5x/2x 안내선)
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):
    pass

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_TOPIC_DIR = _METHOD_DIR.parent
_TEMPO_RAW = _METHOD_DIR / "out" / "csv" / "tempo_raw.csv"
_BESTDORI_CSV = _TOPIC_DIR.parent / "20260720_audio_feats_analysis" / "out" / "bestdori_bpm.csv"
_OUT_CSV = _METHOD_DIR / "out" / "csv" / "tempo_bestdori_comparison.csv"
_OUT_MD = _METHOD_DIR / "out" / "report" / "tempo_bestdori_mismatch.md"
_OUT_PNG = _METHOD_DIR / "out" / "fig" / "tempo_bestdori_scatter.png"

MISMATCH_THRESHOLD = 0.08  # |ratio - 1| 초과 시 불일치로 간주


def main() -> None:
    tempo = pd.read_csv(_TEMPO_RAW)
    tempo = tempo[(tempo["error"].isna()) | (tempo["error"] == "")]
    tempo = tempo[tempo["bpm_madmom"].notna()].copy()

    bestdori = pd.read_csv(_BESTDORI_CSV)[["idx", "official_bpm"]]

    m = tempo.merge(bestdori, on="idx", how="inner")
    m["ratio"] = m["bpm_madmom"] / m["official_bpm"]
    m["octave_class"] = np.select(
        [m["ratio"].between(0.42, 0.58), m["ratio"].between(1.85, 2.15)],
        ["half(0.5x)", "double(2x)"],
        default="",
    )
    m.to_csv(_OUT_CSV, index=False, encoding="utf-8")

    close = m[m["ratio"].between(1 - MISMATCH_THRESHOLD, 1 + MISMATCH_THRESHOLD)]
    mismatch = m[~m["ratio"].between(1 - MISMATCH_THRESHOLD, 1 + MISMATCH_THRESHOLD)].copy()
    mismatch = mismatch.sort_values("ratio")

    n_total, n_close, n_mismatch = len(m), len(close), len(mismatch)
    n_double = (mismatch["octave_class"] == "double(2x)").sum()
    n_half = (mismatch["octave_class"] == "half(0.5x)").sum()
    n_flagged = mismatch["halftime_flag"].sum()

    lines = [
        "# bpm_madmom vs Bestdori 공식 BPM 비교",
        "",
        f"Bestdori 매칭 곡수: {n_total} / {len(tempo)} (커버곡 등 미매칭 제외)",
        f"오차 {MISMATCH_THRESHOLD*100:.0f}% 이내 일치: {n_close}곡 ({n_close/n_total*100:.1f}%)",
        f"불일치: {n_mismatch}곡 ({n_mismatch/n_total*100:.1f}%) — 이 중 배속(2x) {n_double}곡, "
        f"반절(0.5x) {n_half}곡",
        f"불일치 곡 중 halftime_flag=True로 이미 잡힌 것: {n_flagged}/{n_mismatch} "
        f"({n_flagged/n_mismatch*100:.0f}%) — **즉 halftime_flag는 옥타브 오차 탐지 신뢰도가 낮다.**",
        "",
        "## 밴드별 불일치율 (표본 5곡 미만 제외, 불일치율 내림차순)",
        "",
        "| band | n | 불일치 | 불일치율 |",
        "|---|---|---|---|",
    ]
    band_stats = (
        m.assign(mismatch=~m["ratio"].between(1 - MISMATCH_THRESHOLD, 1 + MISMATCH_THRESHOLD))
        .groupby("band")
        .agg(n=("idx", "size"), mismatch=("mismatch", "sum"))
    )
    band_stats = band_stats[band_stats["n"] >= 5].copy()
    band_stats["rate"] = band_stats["mismatch"] / band_stats["n"] * 100
    band_stats = band_stats.sort_values("rate", ascending=False)
    for band, r in band_stats.iterrows():
        lines.append(f"| {band} | {int(r['n'])} | {int(r['mismatch'])} | {r['rate']:.1f}% |")
    lines += [
        "",
        "## 불일치 곡 목록 (ratio 오름차순)",
        "",
        "| idx | band | song | bpm_madmom | official_bpm | ratio | octave_class | halftime_flag |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for _, r in mismatch.iterrows():
        lines.append(
            f"| {r['idx']} | {r['band']} | {r['song']} | {r['bpm_madmom']:.1f} | "
            f"{r['official_bpm']:.1f} | {r['ratio']:.3f} | {r['octave_class']} | {r['halftime_flag']} |"
        )
    _OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {_OUT_MD}")

    # 산점도
    fig, ax = plt.subplots(figsize=(7, 7))
    colors = np.where(
        m["ratio"].between(1 - MISMATCH_THRESHOLD, 1 + MISMATCH_THRESHOLD), "#2a78d6", "#e34948"
    )
    ax.scatter(m["official_bpm"], m["bpm_madmom"], c=colors, s=14, alpha=0.7, linewidths=0)

    lo, hi = 60, 340
    xs = np.linspace(lo, hi, 100)
    ax.plot(xs, xs, color="#898781", lw=1, ls="-", label="1:1 (일치)")
    ax.plot(xs, xs * 2, color="#898781", lw=1, ls="--", label="2x (배속 오차)")
    ax.plot(xs, xs * 0.5, color="#898781", lw=1, ls=":", label="0.5x (반절 오차)")
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_xlabel("official_bpm (Bestdori)")
    ax.set_ylabel("bpm_madmom")
    ax.set_title(f"madmom vs Bestdori 공식 BPM (n={n_total}, 불일치 {n_mismatch}곡)")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(_OUT_PNG, dpi=150)
    print(f"저장: {_OUT_PNG}")

    print(f"저장: {_OUT_CSV}")
    print(f"전체 {n_total} / 일치 {n_close} / 불일치 {n_mismatch} "
          f"(배속 {n_double}, 반절 {n_half}, halftime_flag 탐지 {n_flagged})")


if __name__ == "__main__":
    main()
