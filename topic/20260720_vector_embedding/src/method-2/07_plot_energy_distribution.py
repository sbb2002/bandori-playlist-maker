"""앱의 현행 강도(Song.energy) 기준으로 전체·밴드별 분포를 바이올린 플롯으로 그린다.

`song_repo.load_songs()`가 산출하는 합성 강도와 동일한 값(= out/song_acoustics.csv 의
`intensity`)을 쓴다. songs_master.csv 의 `energy`·`energy_proxy` 컬럼이 아니다 —
그쪽은 발췌 구간 기반이라 무효/역전이다(report/02-acoustic_feature_audit.md).

곡 수가 적은 밴드(n<5)는 KDE가 성립하지 않으므로 바이올린 대신 점으로 표시한다.

출력: fig/energy_distribution_by_band.png
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import config

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 한글 라벨용 — Windows 기본 폰트
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

MIN_N_FOR_VIOLIN = 5


def main():
    src = config.OUT_DIR / "song_acoustics.csv"
    if not src.exists():
        print(f"ERROR: {src} 없음. 02_build_acoustics.py 를 먼저 실행할 것.")
        sys.exit(1)

    df = pd.read_csv(src)
    fig_dir = config.OUT_DIR.parent / "fig"  # method-2/fig — assoc_heatmap.png 과 같은 위치
    fig_dir.mkdir(parents=True, exist_ok=True)

    # 중앙값 내림차순 — 읽기 쉽게
    order = df.groupby("band")["intensity"].median().sort_values(ascending=False).index.tolist()
    groups = [("전체", df["intensity"].values)] + [
        (b, df.loc[df["band"] == b, "intensity"].values) for b in order
    ]

    fig, ax = plt.subplots(figsize=(15, 7))
    positions = np.arange(len(groups))

    # 바이올린 (n>=5 인 것만)
    vio_pos = [i for i, (_, v) in enumerate(groups) if len(v) >= MIN_N_FOR_VIOLIN]
    vio_dat = [groups[i][1] for i in vio_pos]
    parts = ax.violinplot(vio_dat, positions=vio_pos, widths=0.8,
                          showextrema=False, showmedians=False)
    for i, body in zip(vio_pos, parts["bodies"]):
        body.set_facecolor("#4C72B0" if i else "#888888")  # 전체는 회색
        body.set_alpha(0.75 if i else 0.55)
        body.set_edgecolor("#2A2A2A")
        body.set_linewidth(0.8)

    # 개별 곡 점 + 중앙값 — 표본이 작은 밴드도 이 경로로 보인다
    rng = np.random.default_rng(config.SEED)
    for i, (name, v) in enumerate(groups):
        if name == "전체":
            continue  # 661개 점은 노이즈일 뿐
        jitter = rng.uniform(-0.09, 0.09, size=len(v))
        ax.scatter(np.full(len(v), i) + jitter, v, s=7, color="#1A1A1A",
                   alpha=0.35, zorder=3, linewidths=0)
    for i, (_, v) in enumerate(groups):
        ax.hlines(np.median(v), i - 0.32, i + 0.32, color="#C44E52", lw=2.4, zorder=4)

    # y축이 0~1 고정이라 위쪽 여백이 없다 — n은 축 라벨에 붙인다(제목과 충돌 방지)
    ax.set_ylim(0.0, 1.0)
    ax.set_xlim(-0.7, len(groups) - 0.3)
    ax.set_xticks(positions)
    ax.set_xticklabels([f"{n}\n(n={len(v)})" for n, v in groups],
                       rotation=30, ha="right", fontsize=9.5)
    ax.get_xticklabels()[0].set_fontweight("bold")
    ax.set_ylabel("강도 (Song.energy, 앱 현행 합성 지표)", fontsize=11)
    ax.set_title(
        "밴드별 강도 분포 — 앱이 실제 선곡에 쓰는 기준 (n=661)\n"
        "빨간 선=중앙값 · 점=개별 곡 · 바이올린은 n≥5 밴드만",
        fontsize=12, pad=14,
    )
    ax.grid(axis="y", alpha=0.25, linestyle=":")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    fig.tight_layout()
    out = fig_dir / "energy_distribution_by_band.png"
    fig.savefig(out, dpi=150)
    print(f"저장: {out}")

    print("\n--- 밴드별 요약 ---")
    summary = df.groupby("band")["intensity"].agg(["count", "median", "mean", "std"]).loc[order]
    print(summary.to_string(float_format=lambda x: f"{x:.3f}"))
    print(f"\n전체: n={len(df)}, 중앙값={df['intensity'].median():.3f}, "
          f"평균={df['intensity'].mean():.3f}, 표준편차={df['intensity'].std():.3f}")


if __name__ == "__main__":
    main()
