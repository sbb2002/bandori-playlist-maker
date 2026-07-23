"""n>=20 라운드 곡 스크리닝 절차 플로차트 렌더링.

notes/Flowchart-of-screening-process.webp(PRISMA 스타일 참고 이미지)와 같은 양식으로 그린다:
serif 폰트, 직사각형 박스, 중앙 세로 흐름 + 우측 분기 박스(제외/병렬 처리), 마지막 박스만 굵게.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle
from PIL import Image

OUT_PATH = Path(__file__).resolve().parent.parent.parent / "notes" / "n20-screening-flowchart.webp"

plt.rcParams["font.family"] = "Batang"

FIG_W, FIG_H = 11, 13.5

# 중앙 박스 (top -> bottom), (x_center, y_center, width, height, text, bold)
CENTER_BOXES = [
    (3.1, 12.6, 4.6, 1.1, "오디오 분석 파이프라인 자격 검증곡\n($N = 661$)", False),
    (3.1, 10.6, 4.6, 1.1, "정규 밴드 모집단 (10개 밴드)\n($N = 654$)", False),
    (3.1, 8.6, 4.6, 1.1, "밴드×PC1 삼분위 균형표집\n본표본\n($N = 70$)", False),
    (3.1, 6.5, 4.6, 1.2, "불완전블록 배정\n$n{\\geq}20$명이 곡당 최소 5명씩 GEMS-9 채점", False),
    (3.1, 4.6, 4.6, 1.2, "고정효과(rater) + 랜덤절편(song) 혼합모형\n→ 곡별 조정점수(BLUP)", False),
    (3.1, 2.5, 4.6, 1.3, "대표 피쳐 17종 × 가중 Spearman\n+ 부트스트랩 CI + BH-FDR\n($|\\rho|{\\geq}0.4$, $q{<}0.05$) → 통과 후보", False),
    (3.1, 0.5, 4.6, 1.1, "홀드아웃 확증 통과\n확정 필터 후보 피쳐", True),
]

# 우측 분기 박스: (x_center, y_center, width, height, text, arrow_from_center_y)
SIDE_BOXES = [
    (8.6, 11.6, 4.2, 1.1,
     "밴드 규모 미달($<$15곡) 또는\n$various\\_artists$ 제외\n($N = 7$)", 12.6),
    (8.6, 9.6, 4.2, 1.1,
     "밴드×PC1 삼분위 셀에서\n미선정 ($N = 559$)", 10.6),
    (8.6, 7.7, 4.2, 1.1,
     "동일 시드 절차로 disjoint\n홀드아웃 확보·봉인 ($N = 25$)", 8.6),
    (8.6, 1.5, 4.2, 1.2,
     "홀드아웃 확증 미달\n(부호 불일치 / CI 비겹침 /\n$|\\rho|{<}0.3$)", 2.5),
]


def draw_box(ax, x, y, w, h, text, bold=False):
    rect = Rectangle((x - w / 2, y - h / 2), w, h, facecolor="white",
                      edgecolor="black", linewidth=1.3, zorder=2)
    ax.add_patch(rect)
    ax.text(x, y, text, ha="center", va="center", fontsize=11,
             fontweight="bold" if bold else "normal", zorder=3)


def draw_arrow(ax, xy_from, xy_to):
    arrow = FancyArrowPatch(xy_from, xy_to, arrowstyle="-|>", mutation_scale=16,
                             linewidth=1.3, color="black", zorder=1)
    ax.add_patch(arrow)


def main():
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(-0.3, 13.4)
    ax.axis("off")

    for x, y, w, h, text, bold in CENTER_BOXES:
        draw_box(ax, x, y, w, h, text, bold)

    # 중앙 흐름 화살표(위->아래, 박스 사이)
    for i in range(len(CENTER_BOXES) - 1):
        x1, y1, w1, h1, _, _ = CENTER_BOXES[i]
        x2, y2, w2, h2, _, _ = CENTER_BOXES[i + 1]
        draw_arrow(ax, (x1, y1 - h1 / 2), (x2, y2 + h2 / 2))

    for x, y, w, h, text, from_y in SIDE_BOXES:
        draw_box(ax, x, y, w, h, text, bold=False)
        cx, cw = CENTER_BOXES[0][0], CENTER_BOXES[0][2]
        draw_arrow(ax, (cx + cw / 2, from_y), (x - w / 2, y))

    plt.tight_layout()
    png_path = OUT_PATH.with_suffix(".png")
    fig.savefig(png_path, dpi=180, facecolor="white")
    plt.close(fig)

    Image.open(png_path).convert("RGB").save(OUT_PATH, "WEBP", quality=92)
    png_path.unlink()
    print(f"-> {OUT_PATH}")


if __name__ == "__main__":
    main()
