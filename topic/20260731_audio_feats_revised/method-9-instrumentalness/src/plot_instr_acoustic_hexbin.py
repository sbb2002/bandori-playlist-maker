"""instr_stem_ratio(method-9) x acoustic_median(method-8) 교차 hexbin.

morfonica의 바이올린 편성이 instr_stem_ratio를 밀어올린 것과 별개로, 실제로
"악기 에너지 비중이 크다"는 것과 "청감상 어쿠스틱하다(mood_acoustic)"는 것이
같이 움직이는지 확인하기 위한 교차분석. acoustic_median은 극단적 좌측 쏠림
분포(method-8 참고)라 로그 스케일 색상으로 표시한다.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LogNorm

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

_METHOD9_DIR = Path(__file__).resolve().parent.parent
_TOPIC_DIR = _METHOD9_DIR.parent
_INSTR_CSV = _METHOD9_DIR / "out" / "csv" / "instrumentalness_raw.csv"
_ACOU_CSV = _TOPIC_DIR / "method-8-acousticness" / "out" / "csv" / "acousticness_raw.csv"
_OUT_PNG = _METHOD9_DIR / "out" / "fig" / "instr_acoustic_hexbin.png"


def main() -> None:
    instr = pd.read_csv(_INSTR_CSV)[["idx", "band", "instr_stem_ratio"]]
    acou = pd.read_csv(_ACOU_CSV)[["idx", "acoustic_median"]]
    df = instr.merge(acou, on="idx")
    # acoustic_median=0에 가까운 값이 많아 로그축에 그대로 못 올리므로 작은 offset을 더함
    df["acoustic_log"] = np.log10(df["acoustic_median"] + 1e-6)

    fig, ax = plt.subplots(figsize=(8, 7))
    hb = ax.hexbin(df["instr_stem_ratio"], df["acoustic_log"], gridsize=30,
                    cmap="inferno", mincnt=1, norm=LogNorm())
    fig.colorbar(hb, ax=ax, label="곡 수 (로그 스케일)")

    corr = df["instr_stem_ratio"].corr(df["acoustic_median"])
    ax.set_xlabel("instr_stem_ratio (악기 에너지 비율)")
    ax.set_ylabel("log10(acoustic_median + 1e-6)")
    ax.set_title(f"악기 에너지 비율 x 어쿠스틱 확률 (n={len(df)}, r={corr:.3f})")

    for band, marker in [("morfonica", "^"), ("mygo", "s")]:
        sub = df[df["band"] == band]
        ax.scatter(sub["instr_stem_ratio"], sub["acoustic_log"],
                    s=18, facecolors="none", edgecolors="cyan" if band == "morfonica" else "lime",
                    linewidths=0.8, label=band, marker=marker)
    ax.legend(loc="lower right", fontsize=8)

    fig.tight_layout()
    fig.savefig(_OUT_PNG, dpi=150, bbox_inches="tight")
    print(f"저장: {_OUT_PNG}")
    print(f"전체 상관계수(원값 기준): {corr:.3f}")
    for band in ["morfonica", "mygo"]:
        sub = df[df["band"] == band]
        print(f"{band}: n={len(sub)}, acoustic_median 평균={sub['acoustic_median'].mean():.5f}, "
              f"전체 대비 순위=상대적 {'낮음' if sub['acoustic_median'].mean() < df['acoustic_median'].mean() else '높음'}")


if __name__ == "__main__":
    main()
