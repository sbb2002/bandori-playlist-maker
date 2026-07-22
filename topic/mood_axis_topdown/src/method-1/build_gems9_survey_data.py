"""out/gems9_pilot_candidates.csv에서 segment_survey_tool.html에 심을 곡 데이터를 재생성.

excerpt_start_sec/excerpt_end_sec이 비어 있으면 폴백(0, 30초 인트로)으로 채우고
isFallback=true로 표시한다 — Tool 1(구간 설정 툴)에서 정식 구간을 채운 CSV로 갱신한 뒤
이 스크립트를 다시 돌리면 segment_survey_tool.html의 데이터 블록만 그대로 교체된다
(HTML 구조·JS 로직은 안 건드림).
"""
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
CSV_PATH = Path(__file__).resolve().parent.parent.parent / "out" / "gems9_pilot_candidates.csv"
HTML_PATH = Path(__file__).resolve().parent / "segment_survey_tool.html"

FALLBACK_START, FALLBACK_END = 0, 30


def video_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0]


def load_songs():
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    songs = []
    for r in rows:
        start_raw = (r.get("excerpt_start_sec") or "").strip()
        end_raw = (r.get("excerpt_end_sec") or "").strip()
        is_fallback = not start_raw or not end_raw
        start = float(start_raw) if start_raw else FALLBACK_START
        end = float(end_raw) if end_raw else FALLBACK_END
        songs.append({
            "idx": int(r["idx"]),
            "band": r["band"],
            "song": r["song"],
            "videoId": video_id_from_url(r["url"]),
            "energyFull": float(r["energy_full"]),
            "start": start,
            "end": end,
            "isFallback": is_fallback,
        })
    return songs


def main():
    songs = load_songs()
    data_json = json.dumps(songs, ensure_ascii=False, indent=2)

    if not HTML_PATH.exists():
        print(f"{HTML_PATH} 없음 — 데이터만 출력합니다.\n")
        print(data_json)
        return

    html = HTML_PATH.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<script type="application/json" id="songs-data">\n)(.*?)(\n</script>)',
        re.DOTALL,
    )
    if not pattern.search(html):
        raise SystemExit("songs-data 스크립트 블록을 찾지 못했습니다 — HTML 구조 확인 필요.")
    new_html = pattern.sub(lambda m: m.group(1) + data_json + m.group(3), html, count=1)
    HTML_PATH.write_text(new_html, encoding="utf-8")

    n_fallback = sum(1 for s in songs if s["isFallback"])
    print(f"{len(songs)}곡 반영 -> {HTML_PATH}")
    print(f"  폴백(구간 미확정): {n_fallback}곡")
    print(f"  확정: {len(songs) - n_fallback}곡")


if __name__ == "__main__":
    main()
