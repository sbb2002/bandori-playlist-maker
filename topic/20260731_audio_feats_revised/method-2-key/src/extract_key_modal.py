"""K-S 템플릿을 7개 교회선법(모드)으로 확장해 30곡 표본에 대해 재추정.

배경
----
roselia처럼 고딕록/메탈 성향 밴드는 major/minor 두 선법만으로는 설명 안 되는
Phrygian/Aeolian 등 모드 스케일을 자주 쓴다는 가설 검증. 기존 K-S는 major/minor
24템플릿만 쓰므로, 나머지 5개 선법(Dorian/Phrygian/Lydian/Mixolydian/Locrian)을
추가한 84템플릿(12키 x 7모드)으로 같은 30곡을 재분석해 비교한다.

⚠️ 방법론적 한계: Krumhansl-Kessler의 major/minor 프로파일은 실제 청취실험(probe-tone)
으로 검증된 값이지만, 나머지 5개 모드는 그런 실증 데이터가 없다. 여기서는 "각 모드의
특징음(characteristic tone)에 해당하는 가중치를 major/minor 프로파일에서 맞바꾸는"
방식으로 근사 템플릿을 만든다(예: Phrygian = Aeolian에서 b2/2 가중치를 교환).
이건 실증적으로 검증된 값이 아니라 휴리스틱 근사이므로, 결과는 참고용으로만 쓸 것.

표본: bass_key_validation과 동일한 30곡(seed=42, out/bass_key_validation/bass_key_validation.csv
에서 idx 목록만 재사용).

산출물: out/modal_key_validation.csv, out/modal_key_validation_REPORT.md
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_key_ks import (  # noqa: E402
    HOP,
    NOTE_NAMES,
    SR,
    WINDOW_SEC,
    MAJOR_PROFILE,
    MINOR_PROFILE,
    _chroma_to_template_match,
    _majority_vote,
    _rotate_profile,
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
BASS_VAL_CSV = _METHOD_DIR / "out" / "bass_key_validation" / "bass_key_validation.csv"
OUT_CSV = _METHOD_DIR / "out" / "csv" / "modal_key_validation.csv"
OUT_REPORT = _METHOD_DIR / "out" / "report" / "modal_key_validation_REPORT.md"


def _swap(profile: list[float], i: int, j: int) -> list[float]:
    p = list(profile)
    p[i], p[j] = p[j], p[i]
    return p


def build_mode_base_profiles() -> dict[str, list[float]]:
    """Ionian/Aeolian(=기존 major/minor)에서 나머지 5개 모드를 파생.

    인덱스: 0=C(tonic),1=C#(b2),2=D(2),3=D#(b3),4=E(3),5=F(4),
            6=F#(#4/b5),7=G(5),8=G#(b6),9=A(6),10=A#(b7),11=B(7)
    """
    ionian = list(MAJOR_PROFILE)
    aeolian = list(MINOR_PROFILE)

    dorian = _swap(aeolian, 8, 9)          # b6 <-> 6 (자연6도로)
    phrygian = _swap(aeolian, 1, 2)        # b2 <-> 2 (b2 강조)
    lydian = _swap(ionian, 5, 6)           # 4 <-> #4 (#4 강조)
    mixolydian = _swap(ionian, 10, 11)     # b7 <-> 7 (b7 강조)
    locrian = _swap(_swap(aeolian, 1, 2), 6, 7)  # b2 강조 + b5 강조

    return {
        "ionian": ionian,       # = major
        "dorian": dorian,
        "phrygian": phrygian,
        "lydian": lydian,
        "mixolydian": mixolydian,
        "aeolian": aeolian,     # = minor
        "locrian": locrian,
    }


MODE_FAMILY = {  # 장/단조 계열 분류(비교용)
    "ionian": "major", "lydian": "major", "mixolydian": "major",
    "aeolian": "minor", "dorian": "minor", "phrygian": "minor", "locrian": "minor",
}


def build_modal_templates() -> dict[str, tuple[str, list[float]]]:
    base = build_mode_base_profiles()
    templates = {}
    for shift in range(12):
        key = NOTE_NAMES[shift]
        for mode_name, profile in base.items():
            templates[f"{key}_{mode_name}"] = (mode_name, _rotate_profile(profile, shift))
    return templates


def sliding_window_modal_keys(path: Path, templates: dict, window_sec: float = WINDOW_SEC):
    import librosa

    y, sr = librosa.load(str(path), sr=SR, mono=True)
    dur = float(len(y) / sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    frame_times = librosa.frames_to_time(np.arange(chroma.shape[1]), sr=sr, hop_length=HOP)
    window_frames = int(window_sec * sr / HOP)
    stride_frames = window_frames // 2

    windows = []
    for start_frame in range(0, chroma.shape[1], stride_frames):
        end_frame = min(start_frame + window_frames, chroma.shape[1])
        if end_frame - start_frame < window_frames // 2:
            continue
        chroma_win = chroma[:, start_frame:end_frame].mean(axis=1)
        key, mode, corr = _chroma_to_template_match(chroma_win, templates)
        windows.append({
            "window_start_sec": round(float(frame_times[start_frame]), 2),
            "window_end_sec": round(float(frame_times[end_frame - 1]), 2),
            "key": key, "mode": mode, "corr": round(corr, 4),
        })
    return windows, dur


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    bass_val = pd.read_csv(BASS_VAL_CSV)
    target_idx = bass_val["idx"].tolist()
    print(f"대상 {len(target_idx)}곡: {target_idx}")

    master = pd.read_csv(MASTER_CSV)
    key_raw = pd.read_csv(KEY_RAW_CSV)
    templates = build_modal_templates()
    print(f"템플릿 {len(templates)}개(12키 x 7모드) 생성 완료")

    rows = []
    for i, idx in enumerate(target_idx, 1):
        m = master[master["idx"] == idx].iloc[0]
        band, song = m["band"], m["song"]
        file_idx = int(m["file_idx"]) if "file_idx" in m and pd.notna(m["file_idx"]) else int(idx)
        path = AUDIO_FULL_DIR / f"{band}__{file_idx:03d}.wav"
        if not path.exists():
            print(f"  [{i}/{len(target_idx)}] SKIP idx={idx} 오디오 없음: {path.name}")
            continue

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
        print(f"  [{i}/{len(target_idx)}] idx={idx} {band} — K-S:{key_ks}/{mode_ks} -> "
              f"Modal:{key_modal}/{mode_modal}(conf={conf_modal:.3f})")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n저장: {OUT_CSV}")

    n = len(df)
    n_non_mm = df["is_non_major_minor"].sum()
    fam_agree = df["family_agrees_with_ks"].mean()
    roselia = df[df["band"] == "roselia"]

    report = [
        "# 모드 스케일 확장 key 검증 (30곡, K-S major/minor 2모드 -> 7개 교회선법)",
        "",
        "## 방법론 한계 (필독)",
        "",
        "Krumhansl-Kessler major/minor 프로파일은 실증 청취실험 기반이지만, 나머지 5개",
        "모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)는 그런 실증 데이터가 없다.",
        "여기서는 major/minor 프로파일에서 각 모드의 특징음 가중치를 맞바꾸는 방식의",
        "**휴리스틱 근사 템플릿**을 썼다 — 통계적으로 검증된 값이 아니므로 참고용으로만",
        "해석할 것.",
        "",
        f"## 표본: {n}곡 (bass_key_validation과 동일, seed=42)",
        "",
        f"- 장/단조가 아닌 모드(Dorian/Phrygian/Lydian/Mixolydian/Locrian)로 판정된 곡: "
        f"{n_non_mm}/{n} ({n_non_mm/n*100:.1f}%)",
        f"- 모드 판정의 장/단조 계열(family)이 기존 K-S mode_ks와 일치: {fam_agree*100:.1f}%",
        "",
        "## roselia 표본",
        "",
        "| idx | song | K-S | Essentia | Modal(7선법) | non-major/minor |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in roselia.iterrows():
        report.append(
            f"| {r['idx']} | {r['song']} | {r['key_ks']}/{r['mode_ks']} | "
            f"{r['key_essentia']}/{r['mode_essentia']} | {r['key_modal']}/{r['mode_modal']} | "
            f"{r['is_non_major_minor']} |"
        )

    report += ["", "## 전체 30곡 상세", "",
               "| idx | band | K-S | Essentia | Modal | conf |",
               "|---|---|---|---|---|---|"]
    for _, r in df.iterrows():
        report.append(
            f"| {r['idx']} | {r['band']} | {r['key_ks']}/{r['mode_ks']} | "
            f"{r['key_essentia']}/{r['mode_essentia']} | {r['key_modal']}/{r['mode_modal']} | "
            f"{r['modal_confidence']:.3f} |"
        )

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print(f"저장: {OUT_REPORT}")


if __name__ == "__main__":
    main()
