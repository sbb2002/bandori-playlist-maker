"""GEMS-9 라운드2 — 미통과 4항목(wonder/transcendence/power/sadness) 재검증용 서브셋 생성.

report/01(§4)에서 지적한 구간 선택 confound(인트로=저에너지라 고각성 항목이 약하게
채점됐을 가능성)를 저비용으로 확인하기 위해, 라운드1(인트로 기준) 채점에서 이 4항목의
극단값(top3/bottom3)을 보인 곡만 뽑아 하이라이트 구간으로 다시 채점한다. 이번엔 사람이
바뀌는 게 아니라 같은 라벨러가 구간만 바꿔 다시 채점하는 것이므로 여전히 n=1 확인이다
(§2e 표본 계획의 n=1 파일럿 연장선, 다인원 확대와는 별개).

산출물:
- out/gems9_round2_highlight_candidates.csv (서브셋, 구간·9항목 전부 공란 — 재채점용)
- src/method-1/segment_picker_tool_round2.html (Tool 1 라운드2 버전)
- src/method-1/segment_survey_tool_round2.html (Tool 2 라운드2 버전)
두 HTML 모두 localStorage 키·다운로드 파일명을 라운드1과 다르게 줘서 진행 상태가 서로
덮어쓰지 않게 한다.
"""
import csv
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[4]
ROUND1_CSV = Path(__file__).resolve().parent.parent.parent / "out" / "gems9_pilot_candidates.csv"
ROUND2_CSV = Path(__file__).resolve().parent.parent.parent / "out" / "gems9_round2_highlight_candidates.csv"

PICKER_SRC = Path(__file__).resolve().parent / "segment_picker_tool.html"
PICKER_OUT = Path(__file__).resolve().parent / "segment_picker_tool_round2.html"
SURVEY_SRC = Path(__file__).resolve().parent / "segment_survey_tool.html"
SURVEY_OUT = Path(__file__).resolve().parent / "segment_survey_tool_round2.html"

FAILED_ITEMS = ["wonder", "transcendence", "power", "sadness"]
GEMS9_ITEMS = [
    "wonder", "transcendence", "tenderness", "nostalgia", "peacefulness",
    "power", "joyful_activation", "tension", "sadness",
]
N_EXTREME = 3  # 항목당 top N + bottom N


def video_id_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1].split("?")[0]


def select_subset():
    rows = list(csv.DictReader(open(ROUND1_CSV, encoding="utf-8-sig")))
    picked_idx = {}
    for item in FAILED_ITEMS:
        scored = [(float(r[item]), r) for r in rows if (r.get(item) or "").strip()]
        scored.sort(key=lambda t: t[0])
        extremes = scored[:N_EXTREME] + scored[-N_EXTREME:]
        for _, r in extremes:
            picked_idx[int(r["idx"])] = r
    return sorted(picked_idx.values(), key=lambda r: (r["band"], r["song"]))


def write_round2_csv(subset):
    ROUND2_CSV.parent.mkdir(parents=True, exist_ok=True)
    header = (
        ["idx", "band", "song", "url", "energy_full", "excerpt_start_sec", "excerpt_end_sec"]
        + GEMS9_ITEMS + ["rater_note"]
    )
    with open(ROUND2_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in subset:
            w.writerow(
                [r["idx"], r["band"], r["song"], r["url"], r["energy_full"], "", ""]
                + [""] * len(GEMS9_ITEMS) + [""]
            )
    print(f"{len(subset)}곡 -> {ROUND2_CSV}")


def patch(path_in, path_out, replacements, json_pattern, json_data, label):
    text = path_in.read_text(encoding="utf-8")
    if not json_pattern.search(text):
        raise SystemExit(f"{path_in}: {label} 블록을 찾지 못함 — 구조 확인 필요.")
    text = json_pattern.sub(lambda m: m.group(1) + json_data + m.group(2), text, count=1)
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"{path_in}: 치환 대상 '{old}' 없음 — 구조 확인 필요.")
        text = text.replace(old, new)
    path_out.write_text(text, encoding="utf-8")
    print(f"  -> {path_out}")


def build_picker(subset):
    songs = [
        {"idx": int(r["idx"]), "band": r["band"], "song": r["song"],
         "videoId": video_id_from_url(r["url"]), "energyFull": float(r["energy_full"])}
        for r in subset
    ]
    data_json = json.dumps(songs, ensure_ascii=False, indent=2)
    pattern = re.compile(
        r'(<script type="application/json" id="songs-data">\n).*?(\n</script>)', re.DOTALL
    )
    patch(
        PICKER_SRC, PICKER_OUT,
        [
            ("gems9_segment_tool_v1", "gems9_segment_tool_round2_v1"),
            ("gems9_pilot_candidates_segments.csv", "gems9_round2_highlight_segments.csv"),
            ("gems9_pilot_candidates_segments.txt", "gems9_round2_highlight_segments.txt"),
        ],
        pattern, data_json, "songs-data script(picker)",
    )


def build_survey():
    """out/gems9_round2_highlight_candidates.csv의 현재 구간 값을 그대로 반영.

    Tool 1 라운드2에서 구간을 채운 뒤 이 함수를 다시 돌리면(= 스크립트 재실행) 최신 구간이
    Tool 2 라운드2에 반영된다. select_subset()으로 다시 뽑지 않고 이미 만들어진
    ROUND2_CSV를 그대로 읽는다 — 재실행해도 사용자가 채워둔 구간을 덮어쓰지 않기 위함.
    """
    rows = list(csv.DictReader(open(ROUND2_CSV, encoding="utf-8-sig")))
    songs = []
    for r in rows:
        start_raw = (r.get("excerpt_start_sec") or "").strip()
        end_raw = (r.get("excerpt_end_sec") or "").strip()
        is_fallback = not start_raw or not end_raw
        songs.append({
            "idx": int(r["idx"]), "band": r["band"], "song": r["song"],
            "videoId": video_id_from_url(r["url"]), "energyFull": float(r["energy_full"]),
            "start": float(start_raw) if start_raw else 0,
            "end": float(end_raw) if end_raw else 30,
            "isFallback": is_fallback,
        })
    data_json = json.dumps(songs, ensure_ascii=False, indent=2)
    pattern = re.compile(
        r'(<script type="application/json" id="songs-data">\n).*?(\n</script>)', re.DOTALL
    )
    patch(
        SURVEY_SRC, SURVEY_OUT,
        [
            ("gems9_survey_tool_v1", "gems9_survey_tool_round2_v1"),
            ("gems9_survey_responses.csv", "gems9_round2_highlight_responses.csv"),
            ("gems9_survey_responses.txt", "gems9_round2_highlight_responses.txt"),
        ],
        pattern, data_json, "songs-data script(survey)",
    )


def main():
    if ROUND2_CSV.exists():
        print(f"{ROUND2_CSV} 이미 있음 — 서브셋 재선정 없이 Tool 2 라운드2만 최신 구간으로 재동기화.")
        build_survey()
        print("완료. 구간이 더 안 채워졌다면(폴백 표시) Tool 1 라운드2에서 마저 채운 뒤 다시 실행하세요.")
        return

    subset = select_subset()
    print(f"라운드1 극단값 기준 서브셋: {len(subset)}곡 (항목당 top{N_EXTREME}+bottom{N_EXTREME}, 중복 제거)")
    for r in subset:
        print(f"  {r['band']:>20s} / {r['song']}")
    write_round2_csv(subset)
    build_picker(subset)
    build_survey()
    print("\n다음: Tool 1 라운드2(segment_picker_tool_round2.html)로 하이라이트 구간 지정 → "
          "CSV 내보내기 → out/gems9_round2_highlight_candidates.csv 갱신(엑셀/직접 붙여넣기) → "
          "이 스크립트 재실행(Tool 2 재동기화) → Tool 2 라운드2로 채점.")


if __name__ == "__main__":
    main()
