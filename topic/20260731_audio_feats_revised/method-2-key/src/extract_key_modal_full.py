"""K-S 템플릿을 7개 교회선법(모드)으로 확장해 736곡 전체에 재추정.

`extract_key_modal.py`(30/50곡 표본용)를 대상 목록만 736곡 전체로 바꿔 재실행하는
버전. 로직(템플릿 생성, 슬라이딩 윈도우, 다수결)은 원본 함수를 그대로 import해
재사용한다 — 파라미터가 조금이라도 달라지면 기존 50곡 결과와 비교가 무의미해지므로
새로 작성하지 않는다.

오디오 분리가 필요 없는 chroma 상관계수 계산만 하므로 베이스 스템 실험보다 훨씬
빠르다(736곡을 CPU만으로 처리).

산출물
------
- `out/modal_key_validation_full.csv` — 736곡 전체 (기존 50행 modal_key_validation.csv는
  절대 덮어쓰지 않음 — 별도 파일)
- `out/modal_key_validation_full_REPORT.md` — 736곡 기준 통계, roselia/morfonica 전체 분포

실행
----
    python src/extract_key_modal_full.py               # 전곡
    python src/extract_key_modal_full.py --limit 5      # 테스트
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_key_ks import (  # noqa: E402
    _majority_vote,
)
from extract_key_modal import (  # noqa: E402
    MODE_FAMILY,
    build_modal_templates,
    sliding_window_modal_keys,
)

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_TOPIC_DIR = _METHOD_DIR.parent
_REPO_ROOT = _TOPIC_DIR.parents[1]
_MYPROJECTS_ROOT = _REPO_ROOT.parent

MASTER_CSV = _REPO_ROOT / "data" / "songs_master.csv"
AUDIO_FULL_DIR = (
    _MYPROJECTS_ROOT / "bandori-song-sorter" / "src" / "content" / "cluster" / "audio_full"
)
KEY_RAW_CSV = _METHOD_DIR / "out" / "csv" / "key_raw.csv"
OUT_CSV = _METHOD_DIR / "out" / "csv" / "modal_key_validation_full.csv"
OUT_REPORT = _METHOD_DIR / "out" / "report" / "modal_key_validation_full_REPORT.md"


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="모드 스케일 확장 key 검증 (736곡 전체)")
    ap.add_argument("--limit", type=int, default=None, help="처리 곡 수 제한(테스트)")
    args = ap.parse_args()

    master = pd.read_csv(MASTER_CSV)
    key_raw = pd.read_csv(KEY_RAW_CSV)
    templates = build_modal_templates()
    print(f"대상 {len(master)}곡, 템플릿 {len(templates)}개(12키 x 7모드) 생성 완료", flush=True)

    if args.limit is not None:
        master = master.head(args.limit)

    rows = []
    failed = []
    t_start = time.time()
    n = len(master)
    for i, m in enumerate(master.itertuples(index=False), 1):
        idx = int(m.idx)
        band, song = m.band, m.song
        file_idx = int(m.file_idx) if pd.notna(getattr(m, "file_idx", None)) else idx
        path = AUDIO_FULL_DIR / f"{band}__{file_idx:03d}.wav"
        if not path.exists():
            print(f"  [{i}/{n}] SKIP idx={idx} 오디오 없음: {path.name}", flush=True)
            failed.append((idx, band, song, "오디오 없음"))
            continue

        try:
            windows, dur = sliding_window_modal_keys(path, templates)
            agg = _majority_vote(windows)
            key_modal, mode_modal = agg["key_ks"], agg["mode_ks"]
            conf_modal = agg["key_ks_confidence"]

            kr = key_raw[key_raw["idx"] == idx]
            key_ks = kr["key_ks"].values[0] if len(kr) else None
            mode_ks = kr["mode_ks"].values[0] if len(kr) else None
            key_essentia = kr["key_essentia"].values[0] if len(kr) else None
            mode_essentia = kr["mode_essentia"].values[0] if len(kr) else None

            rows.append({
                "idx": idx, "band": band, "song": song,
                "key_ks": key_ks, "mode_ks": mode_ks,
                "key_essentia": key_essentia, "mode_essentia": mode_essentia,
                "key_modal": key_modal, "mode_modal": mode_modal,
                "mode_modal_family": MODE_FAMILY.get(mode_modal),
                "modal_confidence": conf_modal,
                "is_non_major_minor": mode_modal not in ("ionian", "aeolian"),
                "family_agrees_with_ks": (MODE_FAMILY.get(mode_modal) == mode_ks),
            })
        except Exception as exc:
            print(f"  [{i}/{n}] ERR idx={idx} {band} {str(song)[:30]}: {repr(exc)[:150]}", flush=True)
            failed.append((idx, band, song, repr(exc)))
            continue

        if i % 20 == 0 or i == n:
            el = time.time() - t_start
            rate = i / el if el > 0 else 0
            eta = (n - i) / rate if rate > 0 else 0
            print(
                f"  진행 {i}/{n}  ok={len(rows)} err={len(failed)}  "
                f"{rate:.2f}곡/s  ETA {eta/60:.1f}분  경과 {el/60:.1f}분",
                flush=True,
            )

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n저장: {OUT_CSV} ({len(df)}행)", flush=True)
    if failed:
        print(f"실패 {len(failed)}건:", flush=True)
        for idx, band, song, err in failed:
            print(f"  idx={idx} {band} {str(song)[:40]}: {err[:120]}", flush=True)

    n_total = len(df)
    n_non_mm = int(df["is_non_major_minor"].sum())
    fam_agree = df["family_agrees_with_ks"].mean()

    report = [
        "# 모드 스케일 확장 key 검증 (736곡 전체, K-S major/minor 2모드 -> 7개 교회선법)",
        "",
        "## 방법론 한계 (필독)",
        "",
        "Krumhansl-Kessler major/minor 프로파일은 실증 청취실험 기반이지만, 나머지 5개",
        "모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)는 그런 실증 데이터가 없다.",
        "여기서는 major/minor 프로파일에서 각 모드의 특징음 가중치를 맞바꾸는 방식의",
        "**휴리스틱 근사 템플릿**을 썼다 — 통계적으로 검증된 값이 아니므로 참고용으로만",
        "해석할 것.",
        "",
        f"## 표본: {n_total}곡 (songs_master.csv 전체, 50곡 파일럿의 확장판)",
        "",
        f"- 장/단조가 아닌 모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)로 판정된 곡: "
        f"{n_non_mm}/{n_total} ({n_non_mm/n_total*100:.1f}%)" if n_total else "- (데이터 없음)",
        f"- 모드 판정의 장/단조 계열(family)이 기존 K-S mode_ks와 일치: {fam_agree*100:.1f}%"
        if n_total else "",
        f"- 실패(오디오 없음/에러): {len(failed)}곡",
        "",
        "## 밴드별 non-major/minor 비율",
        "",
        "| band | n | non_major_minor | 비율 |",
        "|---|---|---|---|",
    ]
    band_stats = df.groupby("band")["is_non_major_minor"].agg(["sum", "count"])
    band_stats["pct"] = band_stats["sum"] / band_stats["count"] * 100
    band_stats = band_stats.sort_values("pct", ascending=False)
    for band, r in band_stats.iterrows():
        report.append(f"| {band} | {int(r['count'])} | {int(r['sum'])} | {r['pct']:.1f}% |")

    # roselia / morfonica 상세: mode_modal 분포
    for target_band in ("roselia", "morfonica"):
        sub = df[df["band"] == target_band]
        if len(sub) == 0:
            continue
        report += ["", f"## {target_band} 전체 ({len(sub)}곡) mode_modal 분포", "",
                   "| mode_modal | 곡수 | 비율 |", "|---|---|---|"]
        vc = sub["mode_modal"].value_counts()
        for mode_name, cnt in vc.items():
            report.append(f"| {mode_name} | {cnt} | {cnt/len(sub)*100:.1f}% |")

        if target_band == "roselia":
            phryg_pct = (sub["mode_modal"] == "phrygian").mean() * 100
            report.append("")
            report.append(f"- Phrygian 비율: {phryg_pct:.1f}% ({int((sub['mode_modal']=='phrygian').sum())}/{len(sub)})")

        if target_band == "morfonica":
            minor_ks = sub[sub["mode_ks"] == "minor"]
            if len(minor_ks) > 0:
                actually_phrygian = (minor_ks["mode_modal"] == "phrygian").mean() * 100
                report.append("")
                report.append(
                    f"- K-S에서 minor로 분류된 {len(minor_ks)}곡 중 실제로는 Phrygian으로 재분류된 비율: "
                    f"{actually_phrygian:.1f}% ({int((minor_ks['mode_modal']=='phrygian').sum())}/{len(minor_ks)})"
                )

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print(f"저장: {OUT_REPORT}", flush=True)


if __name__ == "__main__":
    main()
