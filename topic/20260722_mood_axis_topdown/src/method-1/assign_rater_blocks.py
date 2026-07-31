"""GEMS-9 n>=20 라운드 불완전블록(incomplete block) 응답자-곡 배정.

통계 자문(report/04) 반영: 응답자 1인이 70곡을 전부 채점하면 부담이 너무 크므로, 곡을
겹치는 블록(템플릿) 몇 개로 나눠 응답자마다 블록 하나씩만 배정한다. 개별 응답자마다
서로 다른 무작위 부분집합을 주는 대신, **소수의 블록 템플릿**(원형 슬라이딩 윈도)을 만들고
여러 응답자를 같은 템플릿에 묶는다 — 그래야 구글폼을 응답자 수만큼(20+개)이 아니라
블록 수만큼(4~6개)만 만들면 된다.

사전에 정한 객관적 통과 기준(재추첨은 이 기준 미달일 때만, 결과가 마음에 안 들어서 하면 안 됨):
1. 연결성: 곡-응답자 중복 그래프가 하나로 연결돼 있을 것(원형 슬라이딩 윈도라 구조적으로 항상
   충족되지만, 코드로도 명시적으로 검증한다).
2. 곡별 최소 응답자 수 >= MIN_RATERS_PER_SONG.
"""
import csv
from pathlib import Path

import numpy as np

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "out"
CANDIDATES_PATH = OUT_DIR / "gems9_n20_candidates.csv"

SEED = 20260723

N_RATERS = 22
BLOCK_SIZE = 30
MIN_RATERS_PER_SONG = 5


def load_song_idxs():
    with open(CANDIDATES_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [int(r["idx"]) for r in rows]


def build_blocks(song_idxs, block_size, rng):
    """원형 슬라이딩 윈도로 블록 템플릿 생성. 곡별 커버리지가 최소 2 이상이 되도록
    스트라이드를 자동으로 좁혀가며 블록 수를 늘린다."""
    order = rng.permutation(song_idxs)
    n = len(order)

    stride = max(1, block_size // 2)
    while True:
        n_blocks = -(-n // stride)  # ceil
        blocks = []
        for b in range(n_blocks):
            start = (b * stride) % n
            idxs = [order[(start + i) % n] for i in range(block_size)]
            blocks.append(sorted(set(idxs)))
        coverage = {s: 0 for s in song_idxs}
        for blk in blocks:
            for s in blk:
                coverage[s] += 1
        if min(coverage.values()) >= 2 or stride == 1:
            return blocks, coverage
        stride = max(1, stride - 2)


def check_connectivity(blocks, song_idxs):
    """곡을 노드로, 같은 블록에 속하면 엣지로 보는 그래프의 연결성 확인(BFS)."""
    adj = {s: set() for s in song_idxs}
    for blk in blocks:
        for s in blk:
            adj[s].update(x for x in blk if x != s)

    start = song_idxs[0]
    visited = {start}
    frontier = [start]
    while frontier:
        nxt = []
        for u in frontier:
            for v in adj[u]:
                if v not in visited:
                    visited.add(v)
                    nxt.append(v)
        frontier = nxt
    return len(visited) == len(song_idxs)


def assign_raters(blocks, n_raters, rng):
    """응답자를 블록에 최대한 균등하게(라운드로빈 + 셔플) 배정."""
    order = rng.permutation(n_raters)
    assignment = {}
    for i, rater in enumerate(order):
        assignment[int(rater)] = i % len(blocks)
    return assignment


def per_song_rater_counts(blocks, assignment):
    counts = {}
    for rater, block_id in assignment.items():
        for s in blocks[block_id]:
            counts[s] = counts.get(s, 0) + 1
    return counts


def main():
    song_idxs = load_song_idxs()
    print(f"본표본 곡수: {len(song_idxs)}")

    rng = np.random.default_rng(SEED)
    blocks, coverage = build_blocks(song_idxs, BLOCK_SIZE, rng)
    print(f"블록 템플릿 수: {len(blocks)}, 블록당 곡수: {[len(b) for b in blocks]}")
    print(f"곡별 블록 커버리지 최소/최대: {min(coverage.values())}/{max(coverage.values())}")

    connected = check_connectivity(blocks, song_idxs)
    print(f"연결성 검증: {'통과' if connected else '실패'}")
    if not connected:
        raise RuntimeError("곡-응답자 중복 그래프가 끊어짐 -> 시드/블록 파라미터 재검토 필요")

    assignment = assign_raters(blocks, N_RATERS, rng)
    rater_counts = per_song_rater_counts(blocks, assignment)
    min_raters = min(rater_counts.values())
    print(f"곡별 배정 응답자 수 최소/최대: {min_raters}/{max(rater_counts.values())}")

    if min_raters < MIN_RATERS_PER_SONG:
        raise RuntimeError(
            f"곡당 최소 응답자 수({min_raters}) < 기준({MIN_RATERS_PER_SONG}) "
            "-> N_RATERS/BLOCK_SIZE 조정 후 재실행 필요(결과가 마음에 안 들어서가 아니라 "
            "이 객관적 기준 미달일 때만 재실행)"
        )
    print(f"곡당 최소 응답자 수 기준({MIN_RATERS_PER_SONG}) 충족")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "gems9_n20_rater_block_assignment.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rater_id", "block_id", "n_songs_in_block"])
        for rater, block_id in sorted(assignment.items()):
            w.writerow([rater, block_id, len(blocks[block_id])])
    print(f"-> {OUT_DIR / 'gems9_n20_rater_block_assignment.csv'}")

    with open(OUT_DIR / "gems9_n20_block_definitions.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["block_id", "song_idx"])
        for block_id, blk in enumerate(blocks):
            for s in blk:
                w.writerow([block_id, s])
    print(f"-> {OUT_DIR / 'gems9_n20_block_definitions.csv'}")


if __name__ == "__main__":
    main()
