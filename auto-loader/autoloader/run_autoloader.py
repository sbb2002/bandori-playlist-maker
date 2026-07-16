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
  ⑤ `data` 브랜치에서 커밋·푸시(기본 동작, `--no-git`으로 생략 가능) — **PR 없음, main 병합도
     없음**(2026-07-15 확정, git-rules.md). `data`는 main에 아예 병합되지 않는 독립 브랜치이고,
     배포된 backend가 런타임에 이 브랜치를 직접 원격 fetch하므로(`src/backend/app/repo/
     remote_source.py`) main 병합 자체가 애초에 불필요하다.

사용(오디오 스택 env: numpy/librosa/soundfile/scipy + yt-dlp):
  python auto-loader/autoloader/run_autoloader.py --dry      # 검증(파일 미변경)
  python auto-loader/autoloader/run_autoloader.py --repo-root <data브랜치 워크트리>
                                                               # data/ 반영 + data 브랜치 자동 커밋·푸시
  python auto-loader/autoloader/run_autoloader.py --no-git    # data/ 반영만, 커밋·푸시 생략
  python auto-loader/autoloader/run_autoloader.py --soft    # 아래 참고

soft-run(--soft): 원본 전곡 wav 캐시가 불완전해 intensity_norm 부트스트랩이 불가능한
환경(예: 로컬 오디오 43%만 보유)에서도 신곡 다운로드·나머지 지표는 정상 반영하고 싶을
때 쓴다. i_*(시간분절 강도) 동결 norm만 준비 불가하면 전체를 중단하는 대신, 해당
신곡의 i_*를 같은 밴드 기존 곡 평균으로 임시 대체해 반영하고
data/provisional_intensity.json에 idx를 기록한다(다른 컬럼은 정상 산출 — i_*만 원본
전곡 wav 재추출이 필요한 유일한 계열이라 영향받는 건 이 6컬럼뿐).
**--soft 없이(즉 intensity_norm 부트스트랩이 가능한 "제대로 준비된 환경"에서) 실행하면**,
새 신곡 처리 전에 먼저 provisional_intensity.json에 남은 idx들을 실측 i_*로
재산출해 songs_master.csv/temporal_intensity.csv를 되짚어 갱신(백필)하고 레지스트리에서
제거한다 — merge_data.patch_intensity_rows() 참고.
"""
from __future__ import annotations

import argparse
import json
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

DEFAULT_REPO_ROOT = _THIS_DIR.parents[1]

# 커밋 대상(데이터 산출물 + 동결 norm 4종)
# 2026-07-16: shape_norm.json이 누락돼 있던 버그 수정 — 이 목록에 없어서 한 번도
# data 브랜치에 커밋된 적이 없었고, 로컬에 우연히 남아있던 파일에 의존하고 있었다.
DATA_PATHS = [
    "data/songs_full.csv", "data/audio_map.json",
    "data/song_features_with_proxies.csv", "data/full_audio_features.csv",
    "data/temporal_intensity.csv", "data/songs_master.csv",
    "data/feature_norms.json", "data/energy_full_norm.json",
    "data/intensity_norm.json", "data/shape_norm.json",
    "data/provisional_intensity.json",
]

PROVISIONAL_JSON_REL = "data/provisional_intensity.json"


def _load_provisional(repo_root: Path) -> dict[int, dict]:
    p = repo_root / PROVISIONAL_JSON_REL
    if not p.exists():
        return {}
    return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}


def _save_provisional(repo_root: Path, reg: dict[int, dict]) -> None:
    p = repo_root / PROVISIONAL_JSON_REL
    if not reg:
        p.unlink(missing_ok=True)
        return
    p.write_text(json.dumps({str(k): v for k, v in reg.items()},
                            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _prepare_norms(repo_root: Path, master_rows: list[dict], audio_dir: Path,
                   workers: int, soft: bool
                   ) -> tuple[dict, norms.EnergyFullFrozen, tuple, dict, bool]:
    """동결 norm 4계열 준비(최초 구축 시 기존 행 재현 검증 후 영속화).

    proxy/shape/energy_full은 이미 반영된 CSV 산출물(song_features_with_proxies.csv
    등)에서 구축되므로 원본 wav 캐시가 불완전해도 항상 준비 가능하다. i_*만
    전곡 wav 부트스트랩이 필요해 유일한 취약점이다 — 재현 실패는 보통 로컬의
    wav 캐시 커버리지 부족 때문(예: 285/660곡만 보유).

    soft=False(기본): 구축 실패는 RuntimeError로 즉시 중단(자로 쓸 분포가 원본과
    다르면 신곡 값 전체가 오염되기 때문) — 이 경로에서 성공하면 intensity_ready=True.
    soft=True: i_* 실패만 흡수하고 (None, None)·intensity_ready=False를 반환,
    호출측이 밴드 평균 임시값으로 대체하도록 한다. proxy/shape/energy_full 실패는
    soft에서도 그대로 중단(이 값들은 wav 없이도 항상 구축 가능해야 하므로, 실패
    시 진짜 버그일 가능성이 높다)."""
    data = repo_root / "data"
    p_norms = norms.load_or_build_proxy_norms(
        data / "song_features_with_proxies.csv", data / "feature_norms.json")
    shape_norms = norms.load_or_build_shape_norms(
        data / "song_features_with_proxies.csv", master_rows,
        data / "shape_norm.json")

    # energy_full 분포의 eligibility는 원시 songs_full(중복 업로드 포함) 밴드 카운트.
    with (data / "songs_full.csv").open(encoding="utf-8", newline="") as f:
        import csv as _csv
        songs_full_rows = list(_csv.DictReader(f))
    elig = merge_data.band_eligibility(songs_full_rows)
    ef = norms.EnergyFullFrozen.load_or_build(
        data / "full_audio_features.csv", elig, master_rows,
        data / "energy_full_norm.json")

    norm_json = data / "intensity_norm.json"
    try:
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
                raise RuntimeError(
                    f"i_* 동결 상수 검증 실패(exact {v['exact']}/{v['total']}, "
                    f"max diff {v['max_abs_diff']:.2e}) — wav 캐시 커버리지 부족 의심")
        med, mad = norms.load_intensity_norm(norm_json)
    except Exception as exc:  # noqa: BLE001
        if not soft:
            raise SystemExit(f"‼️ {exc}") from exc
        print(f"⚠️ --soft: intensity_norm 준비 실패({exc}) — "
              "이번 실행의 신곡 i_*는 밴드 평균으로 임시 대체하고 provisional 기록")
        return p_norms, ef, (None, None), shape_norms, False
    return p_norms, ef, (med, mad), shape_norms, True


def _backfill_provisional(repo_root: Path, audio_dir: Path, med, mad,
                          master_rows: list[dict]) -> None:
    """soft-run이 밴드 평균으로 임시 대체했던 i_*를, intensity_norm이 준비된
    이번 run에서 실측값으로 되짚어 갱신.

    provisional로 반영된 곡은 이미 master의 "기존 곡"이라 sources.detect_new가
    더 이상 신곡으로 잡지 않는다 — 즉 그 wav를 처음 받았던 로컬(soft-run 실행처)이
    아닌 다른 로컬(예: 원본 wav 전곡을 가진 메인 로컬)에서 이 run을 돌리면
    audio_dir에 해당 wav가 없는 게 정상이다. 그래서 없으면 master의
    url(band/idx로 조회)로 즉시 재다운로드를 시도한다. 다운로드까지 실패하면
    (네트워크 문제 등) 해당 idx는 레지스트리에 남겨 다음 기회에 재시도한다
    (fail-soft, 멱등)."""
    reg = _load_provisional(repo_root)
    if not reg:
        return
    by_idx = {int(r["idx"]): r for r in master_rows}
    print(f"provisional i_* 백필 대상 {len(reg)}곡 시도…")
    updates: dict[int, dict[str, str]] = {}
    for idx, meta in reg.items():
        wav = audio_dir / f"{meta['band']}__{int(idx):03d}.wav"
        if not wav.exists():
            m = by_idx.get(int(idx))
            if m is None:
                print(f"  ✗ idx={idx}: master에 없음(비정상) — 스킵, 레지스트리 유지")
                continue
            print(f"  [dl] idx={idx} wav 없음 — 재다운로드 시도")
            got = fetch_new.download_one(
                {"band": meta["band"], "idx": idx, "url": m["url"]}, audio_dir)
            if got is None:
                print(f"  ✗ idx={idx}: 재다운로드 실패 — 다음 실행에 재시도")
                continue
            wav = got
        try:
            frames = norms.compute_frames_for(wav)
            updates[idx] = norms.aggregate_intensity(frames, med, mad)
            print(f"  ✅ idx={idx} {meta['band']} 백필 완료")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ idx={idx}: 백필 실패({exc!r}) — 다음 실행에 재시도")
    if not updates:
        return
    merge_data.patch_intensity_rows(repo_root, updates)
    for idx in updates:
        reg.pop(idx, None)
    _save_provisional(repo_root, reg)
    print(f"provisional 백필 완료: {len(updates)}곡 반영, {len(reg)}곡 대기 중")


def _process_song(cand: dict, wav: Path, p_norms: dict,
                  ef: norms.EnergyFullFrozen, med, mad,
                  audio_entries: dict[int, dict], shape_norms: dict,
                  master_rows: list[dict] | None = None) -> dict | None:
    """신곡 1곡 분석(fail-soft). 성공 시 merge_data.merge용 landed dict.

    med/mad가 None(soft-run에서 intensity_norm 준비 실패)이면 i_*는 같은 밴드
    기존 곡 평균으로 대체하고 landed dict에 provisional=True를 표시한다. 참조할
    같은 밴드 실측 행이 하나도 없으면(신설 밴드 등) 이 곡은 fail-soft로 스킵."""
    idx = cand["idx"]
    try:
        entry = audio_entries.get(idx)
        if not entry or entry.get("band") != cand["band"]:
            raise RuntimeError(f"audio_map 엔트리 불일치(idx={idx}): {entry!r}")

        t0 = time.time()
        excerpt = extract_from_wav(wav)                       # 45s excerpt(r5)
        proxies = norms.compute_proxies(excerpt, p_norms)     # 동결 z
        shape = norms.compute_shape(excerpt, shape_norms)     # 동결 z(형제 audio_map 미의존)
        full = extract_features(wav)                          # 전곡 서브피처
        full["extract_sec"] = round(time.time() - t0, 2)
        energy_full = ef.energy_full_for(full)

        provisional = False
        if med is not None:
            frames = norms.compute_frames_for(wav)            # 프레임 강도
            intensity = norms.aggregate_intensity(frames, med, mad)
        else:
            intensity = norms.band_average_intensity(master_rows or [], cand["band"])
            if intensity is None:
                raise RuntimeError(
                    "intensity_norm 미준비 + 같은 밴드 참조 행 없음 — "
                    "soft-run으로도 i_* 대체 불가")
            provisional = True

        tag = "🟡 provisional" if provisional else "✅"
        print(f"  {tag} {cand['band']} · {cand['song']}  (idx={idx} key={excerpt['key']} "
              f"energy_full={energy_full:.3f} i_mean={intensity['i_mean']})")
        return {"cand": cand, "excerpt": excerpt, "proxies": proxies,
                "full_feats": full, "audio_entry": entry, "shape": shape,
                "energy_full": energy_full, "intensity": intensity,
                "provisional": provisional}
    except Exception as exc:  # noqa: BLE001 — 곡별 격리(fail-soft)
        print(f"  ✗ 분석 실패(스킵·다음 실행 재시도): {cand['band']} · {cand['song']} — {exc!r}")
        return None


def _commit_and_push_data(repo_root: Path, landed: list[dict]) -> None:
    """`data` 브랜치에서 데이터 커밋·푸시(PR 없음 — data는 main에 병합되지 않는다, git-rules.md).

    배포된 backend는 이 브랜치를 런타임에 직접 원격 fetch하므로(`src/backend/app/repo/
    remote_source.py`) main과의 병합 자체가 애초에 불필요하다.
    """
    def g(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        p = subprocess.run(["git", "-C", str(repo_root), *args],
                           capture_output=True, text=True, encoding="utf-8")
        if check and p.returncode != 0:
            raise SystemExit(f"‼️ git {' '.join(args[:2])} 실패: {p.stderr.strip()[:300]}")
        return p

    branch = g("branch", "--show-current").stdout.strip()
    if branch != "data":
        raise SystemExit(f"‼️ data 커밋·푸시는 `data` 브랜치에서만 실행(현재: {branch}). "
                         "git-rules.md의 data 브랜치 규칙 참조.")
    # provisional_intensity.json은 조건부 산출물이라 존재할 때만 add 대상에 포함
    # (git add는 없는 pathspec에 에러를 내므로).
    existing_paths = [p for p in DATA_PATHS if (repo_root / p).exists()]
    g("add", "--", *existing_paths)
    if subprocess.run(["git", "-C", str(repo_root), "diff", "--cached", "--quiet"]).returncode == 0:
        print("커밋할 데이터 변경 없음.")
        return
    titles = ", ".join(f"{s['cand']['band']}·{s['cand']['song']}" for s in landed[:5])
    body = "\n".join(f"- {s['cand']['band']} / {s['cand']['song']} "
                     f"(idx={s['cand']['idx']}, {s['cand']['video_id']})" for s in landed)
    g("commit", "-m", f"data: 신곡 자동 반영 {len(landed)}곡 — {titles} [auto]\n\n{body}")
    g("push", "-u", "origin", "data")
    print("data 브랜치 커밋·푸시 완료(PR 없음).")


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
    ap.add_argument("--no-git", action="store_true",
                    help="data 반영 후 커밋·푸시 생략(기본은 자동 커밋·푸시 — 테스트/로컬 확인용)")
    ap.add_argument("--soft", action="store_true",
                    help="intensity_norm 준비 불가 시 중단 대신 i_*를 밴드 평균으로 "
                         "임시 대체하고 provisional 기록(모듈 docstring 참고)")
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
    if a.limit > 0:
        cands = cands[:a.limit]

    # ② 다운로드 우선(신곡 확보는 norm 준비 성패와 무관하게 항상 시도)
    audio_entries = sources.audio_map_entries_by_idx(audio_map)
    wavs = fetch_new.download_all(cands, audio_dir) if cands else {}

    # ③ 동결 norm(soft-run이면 intensity_norm 실패를 흡수)
    p_norms, ef, (med, mad), shape_norms, intensity_ready = _prepare_norms(
        repo_root, master_rows, audio_dir, a.workers, soft=a.soft)

    # ④ 정상(비-soft) run이면, 먼저 이전 soft-run이 남긴 provisional i_*를 백필
    if not a.soft and intensity_ready and not a.dry:
        _backfill_provisional(repo_root, audio_dir, med, mad, master_rows)

    if not cands:
        print("신곡 없음 — 종료(멱등).")
        return 0

    # ⑤ 곡별 처리
    landed, failed = [], []
    for c in cands:
        wav = wavs.get(c["idx"])
        if wav is None:
            print(f"  ✗ 다운로드 실패(스킵): {c['band']} · {c['song']}")
            failed.append(c)
            continue
        res = _process_song(c, wav, p_norms, ef, med, mad, audio_entries, shape_norms,
                            master_rows=master_rows)
        (landed if res else failed).append(res or c)

    print(f"\n반영 {len(landed)}곡 · 실패 {len(failed)}곡")
    if not landed:
        print("반영할 신곡 없음 — 종료.")
        return 1 if failed else 0

    # ⑥ 반영
    if a.dry:
        print("--dry: data/ 미변경. 산출 예정 행:")
        for s in landed:
            row = merge_data.assemble_master_row(
                s["cand"], s["excerpt"], s["proxies"], s["audio_entry"],
                s["energy_full"], s["intensity"],
                True, s["shape"])  # dry에서는 eligible 근사 표기(실반영 시 재계산)
            prov = " [provisional i_*]" if s.get("provisional") else ""
            print(f"  {row}{prov}")
        return 0

    sf_bytes = sources.read_main_bytes(sources.SORTER_SONGS_FULL, sorter)
    am_bytes = sources.read_main_bytes(sources.SORTER_AUDIO_MAP, sorter)
    merge_data.merge(repo_root, landed, sf_bytes, am_bytes)
    print(f"data/ 반영 완료: master {len(master_rows)} → {len(master_rows) + len(landed)}행")

    provisional_landed = [s for s in landed if s.get("provisional")]
    if provisional_landed:
        reg = _load_provisional(repo_root)
        for s in provisional_landed:
            reg[int(s["cand"]["idx"])] = {"band": s["cand"]["band"],
                                          "song": s["cand"]["song"],
                                          "recorded_at": time.strftime("%Y-%m-%d")}
        _save_provisional(repo_root, reg)
        print(f"⚠️ provisional i_* {len(provisional_landed)}곡 기록 — "
              f"{PROVISIONAL_JSON_REL}. intensity_norm 준비되는 run에서 자동 백필됨.")

    # ⑦ git(기본 동작 — data 브랜치 커밋·푸시, --no-git으로 생략 가능)
    if not a.no_git:
        _commit_and_push_data(repo_root, landed)
    else:
        print("(--no-git — data 브랜치 커밋·푸시 생략)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
