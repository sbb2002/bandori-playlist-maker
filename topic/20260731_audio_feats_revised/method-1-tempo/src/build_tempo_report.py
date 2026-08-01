"""tempo_raw.csv를 읽어 전체/밴드별 상위·하위 10곡 tempo 리포트를 만든다.

산출물: ../out/tempo_report.md
- 전체 상위10 / 하위10 (bpm_madmom 기준)
- 밴드별 상위10 / 하위10 (표본 10곡 미만 밴드는 보유곡 전체만, "표본 부족" 주석)
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):
    pass

_THIS_DIR = Path(__file__).resolve().parent
_METHOD_DIR = _THIS_DIR.parent
_IN_CSV = _METHOD_DIR / "out" / "csv" / "tempo_raw.csv"
_OUT_MD = _METHOD_DIR / "out" / "report" / "tempo_report.md"

TOP_N = 10


def load() -> pd.DataFrame:
    df = pd.read_csv(_IN_CSV, dtype={"idx": int, "band": str, "song": str})
    df = df[df["error"].isna() | (df["error"] == "")]
    df = df[df["bpm_madmom"].notna()].copy()
    df["bpm_madmom"] = df["bpm_madmom"].astype(float)
    return df


def table(df: pd.DataFrame) -> str:
    cols = ["idx", "band", "song", "bpm_madmom", "halftime_flag"]
    lines = ["| idx | band | song | bpm_madmom | halftime_flag |",
             "|---|---|---|---|---|"]
    for _, r in df[cols].iterrows():
        lines.append(f"| {r['idx']} | {r['band']} | {r['song']} | {r['bpm_madmom']:.1f} | {r['halftime_flag']} |")
    return "\n".join(lines)


def main() -> None:
    df = load()
    _OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    parts = [
        "# Tempo(bpm_madmom) 상/하위 10곡 리포트",
        "",
        f"**생성일**: {datetime.now().isoformat()}",
        "",
        f"대상: {len(df)}곡 (error 없이 bpm_madmom 산출된 곡만)",
        "",
        "## 전체",
        "",
        "### 상위 10곡 (빠른 순)",
        "",
        table(df.sort_values("bpm_madmom", ascending=False).head(TOP_N)),
        "",
        "### 하위 10곡 (느린 순)",
        "",
        table(df.sort_values("bpm_madmom", ascending=True).head(TOP_N)),
        "",
        "## 밴드별",
        "",
    ]

    band_order = (
        df.groupby("band")["bpm_madmom"].median().sort_values(ascending=False).index.tolist()
    )
    for band in band_order:
        sub = df[df["band"] == band]
        n = len(sub)
        parts.append(f"### {band} (n={n})")
        parts.append("")
        if n < TOP_N:
            parts.append(f"⚠️ 표본 {n}곡 < {TOP_N} — 보유곡 전체를 빠른 순으로 표시(상/하위 구분 무의미).")
            parts.append("")
            parts.append(table(sub.sort_values("bpm_madmom", ascending=False)))
            parts.append("")
            continue
        parts.append(f"**상위 {TOP_N}곡 (빠른 순)**")
        parts.append("")
        parts.append(table(sub.sort_values("bpm_madmom", ascending=False).head(TOP_N)))
        parts.append("")
        parts.append(f"**하위 {TOP_N}곡 (느린 순)**")
        parts.append("")
        parts.append(table(sub.sort_values("bpm_madmom", ascending=True).head(TOP_N)))
        parts.append("")

    _OUT_MD.write_text("\n".join(parts), encoding="utf-8")
    print(f"저장: {_OUT_MD}")


if __name__ == "__main__":
    main()
