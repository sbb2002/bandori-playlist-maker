"""framework.md §2b — pathos 축 후보 생성.

새 표집을 하지 않는다 — mood_warmth 1라운드가 이미 esora 유사도로 뽑아둔 29(+1 중복)곡과
그때 남긴 청취노트를 그대로 재사용한다(`mood_warmth/candidates_worksheet.csv`). 그 라벨
(similarity_rating_1to5)은 "esora 유사도"라 pathos 자체가 아니므로(§2a) 재사용하지 않고
빈 칸으로 남겨, 다음 세션에서 **"애절하나 위로되는가"라는 새 질문으로 같은 곡을 다시 채점**
하게 한다 — 곡 선정 비용은 재사용하되 질문만 교체한다.

청취/라벨링은 이 스크립트가 하지 않는다 — 후보곡 CSV만 만든다.
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC_PATH = ROOT / "topic" / "mood_warmth" / "candidates_worksheet.csv"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "pathos_candidates.csv"


def main():
    rows = list(csv.DictReader(open(SRC_PATH, encoding="utf-8")))
    # rank19(idx 97)는 rank9(idx 91)의 중복곡 — mood_warmth README가 이미 제외 처리
    rows = [r for r in rows if r["idx"] != "97"]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([
            "idx", "band", "song", "url",
            "prior_esora_similarity_1to5", "prior_listener_note",
            "pathos_rating_0to10", "pathos_note",
        ])
        for r in rows:
            w.writerow([
                r["idx"], r["band"], r["song"], r["url"],
                r["similarity_rating_1to5"], r["listener_note"],
                "", "",
            ])

    print(f"{len(rows)}곡 후보(재사용) -> {OUT_PATH}")
    print("주의: prior_esora_similarity_1to5·prior_listener_note는 참고용(예전 질문 기준)이고,")
    print("      pathos_rating_0to10은 '애절하나 위로되는가'라는 새 질문으로 다시 채점할 것.")


if __name__ == "__main__":
    main()
