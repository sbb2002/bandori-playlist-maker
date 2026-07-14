"""신곡 오토로더 원커맨드 — 감별 → 다운로드 → 분석(이 앱 파라미터) → data/ 반영.

형제 프로젝트 semiauto-loader(run_local.py + orchestrate.py)를 이 프로젝트에 맞게
재구성한 로컬 파이프라인. 감지(RSS)는 형제 Actions가 전담하므로 여기서는 하지 않고,
형제 origin/main에 이미 반영된 곡과 우리 master의 차이만 처리한다(sources.py).

흐름(곡별 fail-soft — 실패 곡은 스킵, 다음 실행에서 자동 재시도):
  ① 형제 fetch → 신곡 감별(video_id 기준, 멱등)
  ② 동결 norm 준비·검증(norms.py) — intensity_norm.json 없으면 부트스트랩(1회, 무거움)
  ③ 곡별: yt-dlp 다운로드(집 IP) → 45s excerpt 특징+proxy → 전곡 서브피처 →
     energy_full → 시간분절 i_* → audio_map(bpm/energy/shape) 조인
  ④ data/ 6파일 반영(merge_data.py — 원자적, 실패 시 전체 롤백)
  ⑤ (옵션 --git) `data` 브랜치에서 커밋·푸시 후 main 대상 PR 오픈 —
     **직접 main 머지는 하지 않는다**(CLAUDE.md Working agreement; git-rules.md의
     `data` 브랜치 자동 머지는 PR 자동머지 Actions 도입 후에 적용).

사용(오디오 스택 env: numpy/librosa/soundfile/scipy + yt-dlp):
  python src/scripts/autoloader/run_autoloader.py --dry     # 검증(파일 미변경)
  python src/scripts/autoloader/run_autoloader.py           # data/ 반영(git 없음)
  python src/scripts/autoloader/run_autoloader.py --repo-root <data브랜치 워크트리> --git
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))
_DATA_SCRIPTS = _THIS_DIR.parent / "data"
if str(_DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DATA_SCRIPTS))

import fetch_new  # noqa: E402
import merge_data  # noqa: E402
import norms  # noqa: E402
import sources  # noqa: E402
from excerpt_features import extract_from_wav  # noqa: E402
from extract_full_energy import extract_features  # noqa: E402  (기존 모듈 재사용)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError, OSError):
    pass

DEFAULT_REPO_ROOT = _THIS_DIR.parents[2]

# 커밋 대상(데이터 산출물 + 동결 norm 3종)
DATA_PATHS = [
    "data/songs_full.csv", "data/audio_map.json",
    "data/song_features_with_proxies.csv", "data/full_audio_features.csv",
    "data/temporal_intensity.csv", "data/songs_master.csv",
    "data/feature_norms.json", "data/energy_full_norm.json",
    "data/intensity_norm.json",
]


def _prepare_norms(repo_root: Path, master_rows: list[dict], audio_dir: Path,
                   workers: int) -> tuple[dict, norms.EnergyFullFrozen, tuple]:
    """동결 norm 3계열 준비(최초 구축 시 기존 행 재현 검증 후 영속화).

    구축 실패(재현 불일치)는 RuntimeError로 즉시 중단 — 자로 쓸 분포가 원본과
    다르면 신곡 값 전체가 오염되기 때문."""
    data = repo_root / "data"
    p_norms = norms.load_or_build_proxy_norms(
        data / "song_features_with_proxies.csv", data / "feature_norms.json")

    # energy_full 분포의 eligibility는 원시 songs_full(중복 업로드 포함) 밴드 카운트.
    with (data / "songs_full.csv").open(encoding="utf-8", newline="") as f:
        import csv as _csv
        songs_full_rows = list(_csv.DictReader(f))
    elig = merge_data.band_eligibility(songs_full_rows)
    ef = norms.EnergyFullFrozen.load_or_build(
        data / "full_audio_features.csv", elig, master_rows,
        data / "energy_full_norm.json")

    norm_json = data / "intensity_norm.json"
    if not norm_json.exists():
        print("intensity_norm.json 없음 → 기존 전곡 wav 부트스트랩(1회, 수 분~수십 분)…")
        # ⚠️ 전역 med/MAD의 원본 기반은 master(658)가 아니라 원시 추출 세트
        # temporal_intensity.csv(660행, 중복 업로드 포함)다 — energy_full과 동일 사정.
        with (data / "temporal_intensity.csv").open(encoding="utf-8", newline="") as f:
            import csv as _csv2
            basis_rows = list(_csv2.DictReader(f))
        payload = norms.bootstrap_intensity_norm(basis_rows, audio_dir,
                                                 out_json=norm_json, workers=workers)
        v = payload["verify"]
        if v["total"] == 0 or v["max_abs_diff"] > 5e-4:
            norm_json.unlink(missing_ok=True)
            raise SystemExit("‼️ i_* 동결 상수 검증 실패 — extract_temporal_intensity 대조 필요")
    med, mad = norms.load_intensity_norm(norm_json)
    return p_norms, ef, (med, mad)


def _process_song(cand: dict, wav: Path, p_norms: dict,
                  ef: norms.EnergyFullFrozen, med, mad,
                  audio_entries: dict[int, dict]) -> dict | None:
    """신곡 1곡 분석(fail-soft). 성공 시 merge_data.merge용 landed dict."""
    idx = cand["idx"]
    try:
        entry = audio_entries.get(idx)
        if not entry or entry.get("band") != cand["band"]:
            raise RuntimeError(f"audio_map 엔트리 불일치(idx={idx}): {entry!r}")

        t0 = time.time()
        excerpt = extract_from_wav(wav)                       # 45s excerpt(r5)
        proxies = norms.compute_proxies(excerpt, p_norms)     # 동결 z
        full = extract_features(wav)                          # 전곡 서브피처
        full["extract_sec"] = round(time.time() - t0, 2)
        frames = norms.compute_frames_for(wav)                # 프레임 강도
        intensity = norms.aggregate_intensity(frames, med, mad)
        energy_full = ef.energy_full_for(full)

        print(f"  ✅ {cand['band']} · {cand['song']}  (idx={idx} key={excerpt['key']} "
              f"energy_full={energy_full:.3f} i_mean={intensity['i_mean']})")
        return {"cand": cand, "excerpt": excerpt, "proxies": proxies,
                "full_feats": full, "audio_entry": entry,
                "energy_full": energy_full, "intensity": intensity}
    except Exception as exc:  # noqa: BLE001 — 곡별 격리(fail-soft)
        print(f"  ✗ 분석 실패(스킵·다음 실행 재시도): {cand['band']} · {cand['song']} — {exc!r}")
        return None


def _git_data_branch(repo_root: Path, landed: list[dict]) -> None:
    """`data` 브랜치에서 데이터 커밋·푸시 + main 대상 PR 오픈(머지는 소유자)."""
    def g(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        p = subprocess.run(["git", "-C", str(repo_root), *args],
                           capture_output=True, text=True, encoding="utf-8")
        if check and p.returncode != 0:
            raise SystemExit(f"‼️ git {' '.join(args[:2])} 실패: {p.stderr.strip()[:300]}")
        return p

    branch = g("branch", "--show-current").stdout.strip()
    if branch != "data":
        raise SystemExit(f"‼️ --git은 `data` 브랜치에서만 실행(현재: {branch}). "
                         "git-rules.md의 data 브랜치 규칙 참조.")
    g("add", "--", *DATA_PATHS)
    if subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--quiet"]).returncode == 0:
        print("커밋할 데이터 변경 없음.")
        return
    titles = ", ".join(f"{s['cand']['band']}·{s['cand']['song']}" for s in landed[:5])
    body = "\n".join(f"- {s['cand']['band']} / {s['cand']['song']} "
                     f"(idx={s['cand']['idx']}, {s['cand']['video_id']})" for s in landed)
    g("commit", "-m", f"data: 신곡 자동 반영 {len(landed)}곡 — {titles} [auto]\n\n{body}")
    g("push", "-u", "origin", "data")
    pr = subprocess.run(
        ["gh", "pr", "create", "--base", "main", "--head", "data",
         "--title", f"data: 신곡 자동 반영 {len(landed)}곡 — {titles}",
         "--body", body + "\n\n(자동 생성 — run_autoloader.py. 머지는 저장소 소유자가 수행)"],
        cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8")
    if pr.returncode == 0:
        print(f"PR 오픈: {pr.stdout.strip()}")
    else:
        print(f"⚠️ gh pr create 실패(수동으로 PR 필요): {pr.stderr.strip()[:300]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="신곡 오토로더(감별→다운로드→분석→반영)")
    ap.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT),
                    help="data/를 갱신할 레포 루트(기본: 이 스크립트의 레포). "
                         "data 브랜치 워크트리를 지정할 수 있음")
    ap.add_argument("--sorter-repo", default=str(sources.DEFAULT_SORTER_REPO),
                    help="형제 레포 경로(origin/main 데이터 소스)")
    ap.add_argument("--audio-dir", default=str(fetch_new.DEFAULT_AUDIO_DIR),
                    help="wav 캐시 폴더(기본: 형제 데브 레포 audio_full)")
    ap.add_argument("--dry", action="store_true", help="분석까지 하되 data/ 미변경")
    ap.add_argument("--limit", type=int, default=0, help="이번 실행 최대 곡 수(0=전체)")
    ap.add_argument("--workers", type=int, default=6, help="부트스트랩 병렬 worker")
    ap.add_argument("--git", action="store_true",
                    help="반영 후 data 브랜치 커밋·푸시 + PR 오픈(브랜치=data 필수)")
    a = ap.parse_args(argv)

    repo_root = Path(a.repo_root).resolve()
    sorter = Path(a.sorter_repo).resolve()
    audio_dir = Path(a.audio_dir).resolve()

    # ① 감별
    print(f"형제 레포 fetch: {sorter}")
    sources.fetch_sorter(sorter)
    sorter_rows = sources.load_sorter_songs_full(sorter)
    audio_map = sources.load_sorter_audio_map(sorter)
    master_rows = sources.load_master_rows(repo_root / merge_data.REL_MASTER)
    cands = sources.detect_new(sorter_rows, master_rows)
    print(f"감별: 형제 main {len(sorter_rows)}행 vs master {len(master_rows)}행 "
          f"→ 신곡 {len(cands)}곡")
    for c in cands:
        print(f"  · idx={c['idx']} {c['band']:12} {c['song']}  ({c['video_id']})")
    if not cands:
        print("신곡 없음 — 종료(멱등).")
        return 0
    if a.limit > 0:
        cands = cands[:a.limit]

    # ② 동결 norm
    p_norms, ef, (med, mad) = _prepare_norms(repo_root, master_rows, audio_dir,
                                             a.workers)

    # ③ 곡별 처리
    audio_entries = sources.audio_map_entries_by_idx(audio_map)
    wavs = fetch_new.download_all(cands, audio_dir)
    landed, failed = [], []
    for c in cands:
        wav = wavs.get(c["idx"])
        if wav is None:
            print(f"  ✗ 다운로드 실패(스킵): {c['band']} · {c['song']}")
            failed.append(c)
            continue
        res = _process_song(c, wav, p_norms, ef, med, mad, audio_entries)
        (landed if res else failed).append(res or c)

    print(f"\n반영 {len(landed)}곡 · 실패 {len(failed)}곡")
    if not landed:
        print("반영할 신곡 없음 — 종료.")
        return 1 if failed else 0

    # ④ 반영
    if a.dry:
        print("--dry: data/ 미변경. 산출 예정 행:")
        for s in landed:
            row = merge_data.assemble_master_row(
                s["cand"], s["excerpt"], s["proxies"], s["audio_entry"],
                s["energy_full"], s["intensity"],
                True)  # dry에서는 eligible 근사 표기(실반영 시 재계산)
            print(f"  {row}")
        return 0

    sf_bytes = sources.read_main_bytes(sources.SORTER_SONGS_FULL, sorter)
    am_bytes = sources.read_main_bytes(sources.SORTER_AUDIO_MAP, sorter)
    merge_data.merge(repo_root, landed, sf_bytes, am_bytes)
    print(f"data/ 반영 완료: master {len(master_rows)} → {len(master_rows) + len(landed)}행")

    # ⑤ git(옵션)
    if a.git:
        _git_data_branch(repo_root, landed)
    else:
        print("(git 미실행 — data 브랜치 커밋·PR은 --git 또는 수동으로)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
