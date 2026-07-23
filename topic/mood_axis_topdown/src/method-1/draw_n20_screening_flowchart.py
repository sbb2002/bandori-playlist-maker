"""n>=20 라운드 곡 스크리닝 절차 플로차트 렌더링 (한글판 + 영문판).

notes/Flowchart-of-screening-process.webp(PRISMA 스타일 참고 이미지)와 같은 양식으로 그린다:
serif 폰트, 직사각형 박스, 중앙 세로 흐름 + 우측 분기 박스(제외/병렬 처리), 마지막 박스만 굵게.
"""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle
from PIL import Image

FIG_DIR = Path(__file__).resolve().parent.parent.parent / "fig"

FIG_W, FIG_H = 11, 15.4

TITLE_KO = "최종 선정: 본표본 $N=70$ + 홀드아웃(봉인) $N=25$  =  총 $N=95$곡 (모집단 654곡 중)"
TITLE_EN = "Final selection: main sample $N=70$ + sealed holdout $N=25$  =  total $N=95$ songs (of 654 eligible)"

# 2026-07-23: 본표본(654->70) 구간에 걸린 두 제외/분기 사유(홀드아웃 확보, 미선정)를 한
# 박스에 몰아넣었더니 "칸 하나에 두 사유"라는 지적을 받아 각각 별도 박스로 분리했다.
# 그만큼 세로 공간이 더 필요해 본표본 이하 박스를 전부 아래로 밀어 배치했다(왼쪽 메인
# 흐름도 같이 내려감 — 오른쪽만 늘리고 왼쪽을 그대로 두면 분기 화살표가 어긋난다).

CENTER_BOXES_KO = [
    (3.1, 12.6, 4.6, 1.1, "오디오 분석 파이프라인 자격 검증곡\n($N = 661$)", False),
    (3.1, 10.6, 4.6, 1.1, "정규 밴드 모집단 (10개 밴드)\n($N = 654$)", False),
    (3.1, 8.7, 4.6, 1.0, "본표본($N{=}70$) 제외 나머지\n($N = 584$)", False),
    (3.1, 7.3, 4.6, 1.3, "밴드당 동일 N($7$곡 $\\times$ $10$밴드) x PC1 삼분위\n균형표집\n본표본\n($N = 70$)", False),
    (3.1, 5.2, 4.6, 1.2, "불완전블록 배정\n$n{\\geq}20$명이 곡당 최소 5명씩 GEMS-9 채점", False),
    (3.1, 3.3, 4.6, 1.2, "고정효과(rater) + 랜덤절편(song) 혼합모형\n→ 곡별 조정점수(BLUP)", False),
    (3.1, 1.2, 4.6, 1.3, "대표 피쳐 17종 × 가중 Spearman\n+ 부트스트랩 CI + BH-FDR\n($|\\rho|{\\geq}0.4$, $q{<}0.05$) → 통과 후보", False),
    (3.1, -0.8, 4.6, 1.1, "홀드아웃 확증 통과\n확정 필터 후보 피쳐", True),
]

SIDE_BOXES_KO = [
    (8.6, 11.6, 4.2, 1.1,
     "밴드 규모 미달($<$15곡) 또는\n$various\\_artists$ 제외\n($N = 7$)", 11.6),
    (8.6, 9.6, 4.2, 1.0,
     "동일 시드 절차로 disjoint\n홀드아웃 확보·봉인 ($N = 25$)", 9.6),
    (8.6, 8.08, 4.4, 1.3,
     "밴드×PC1 삼분위 셀에서 무작위\n미추첨: 응답자 부담상 654곡\n전수조사 불가 ($N = 559$)", 8.08),
]

CENTER_BOXES_EN = [
    (3.1, 12.6, 4.6, 1.1, "Eligible songs from audio-analysis pipeline\n($N = 661$)", False),
    (3.1, 10.6, 4.6, 1.1, "Regular-band population (10 bands)\n($N = 654$)", False),
    (3.1, 8.7, 4.6, 1.0, "Remainder after main sample ($N=70$)\n($N = 584$)", False),
    (3.1, 7.3, 4.6, 1.3, "Equal N per band ($7\\times10$ bands) x PC1-tertile\nbalanced sampling\nMain sample\n($N = 70$)", False),
    (3.1, 5.2, 4.6, 1.2, "Incomplete-block assignment\n$n{\\geq}20$ raters, $\\geq$5 raters/song, GEMS-9 scoring", False),
    (3.1, 3.3, 4.6, 1.2, "Mixed model: fixed effect (rater) + random intercept (song)\n→ per-song adjusted score (BLUP)", False),
    (3.1, 1.2, 4.6, 1.3, "17 representative features $\\times$ weighted Spearman\n+ bootstrap CI + BH-FDR\n($|\\rho|{\\geq}0.4$, $q{<}0.05$) → candidate features", False),
    (3.1, -0.8, 4.6, 1.1, "Passed holdout confirmation\nFinal filter candidate features", True),
]

SIDE_BOXES_EN = [
    (8.6, 11.6, 4.2, 1.1,
     "Excluded: band size $<$15 songs, or\n$various\\_artists$\n($N = 7$)", 11.6),
    (8.6, 9.6, 4.2, 1.0,
     "Disjoint holdout drawn from same\nseed sequence, sealed ($N = 25$)", 9.6),
    (8.6, 8.08, 4.4, 1.3,
     "Not drawn within band $\\times$ tertile cells:\nsurveying all 654 songs is infeasible\ngiven rater burden ($N = 559$)", 8.08),
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


def render(center_boxes, side_boxes, font_family, out_path, title):
    plt.rcParams["font.family"] = font_family
    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(-1.5, 14.1)
    ax.axis("off")
    ax.text(5.6, 13.85, title, ha="center", va="center", fontsize=12.5, fontweight="bold")

    for x, y, w, h, text, bold in center_boxes:
        draw_box(ax, x, y, w, h, text, bold)

    for i in range(len(center_boxes) - 1):
        x1, y1, w1, h1, _, _ = center_boxes[i]
        x2, y2, w2, h2, _, _ = center_boxes[i + 1]
        draw_arrow(ax, (x1, y1 - h1 / 2), (x2, y2 + h2 / 2))

    # 제외/분기 화살표: 메인 세로 화살표 중간 지점(branch point)에서 가로로 갈라져 나가는
    # T자 모양으로 그린다(대각선 금지) — 참고 이미지(PRISMA 스타일)와 동일한 표현.
    cx = center_boxes[0][0]
    for x, y, w, h, text, branch_y in side_boxes:
        draw_box(ax, x, y, w, h, text, bold=False)
        draw_arrow(ax, (cx, branch_y), (x - w / 2, branch_y))

    plt.tight_layout()
    png_path = out_path.with_suffix(".png")
    fig.savefig(png_path, dpi=180, facecolor="white")
    plt.close(fig)

    Image.open(png_path).convert("RGB").save(out_path, "WEBP", quality=92)
    png_path.unlink()
    print(f"-> {out_path}")


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    render(CENTER_BOXES_KO, SIDE_BOXES_KO, "Batang",
           FIG_DIR / "n20-screening-flowchart.webp", TITLE_KO)
    render(CENTER_BOXES_EN, SIDE_BOXES_EN, "Times New Roman",
           FIG_DIR / "n20-screening-flowchart-en.webp", TITLE_EN)


if __name__ == "__main__":
    main()
