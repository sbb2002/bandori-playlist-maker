"""신곡 데이터 반영 — data/ 6파일 갱신(원자적: 실패 시 스냅샷 전체 복원).

반영 방식 2종:
  - **통째 복사(mirror)**: `songs_full.csv`·`audio_map.json`은 형제 origin/main의
    바이트를 그대로 기록(build_master._copy_sources와 동일 철학 — 조인 무결성 원본 보장).
  - **append**: `song_features_with_proxies.csv`(형제 측 원본이 삭제돼 우리 사본이
    유일본), `full_audio_features.csv`, `temporal_intensity.csv`, `songs_master.csv`는
    기존 행 **바이트 불변** + 신곡 행만 끝에 추가(동결 norm 원칙, norms.py 참조).

검증(assert — 하나라도 실패하면 전 파일 롤백):
  - append 파일들은 기존 내용의 순수 연장(startswith)이어야 함.
  - master: idx·video_id 전역 유일, video_id 11자, camelot 매핑 성공,
    기존 행 eligible_band 무변동, 행 수 = 기존 + 신곡 수.

표준 라이브러리만 사용(값 계산은 상류 모듈이 완료, 여기는 기록·검증만).
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _THIS_DIR.parents[1]
_DATA_SCRIPTS = _THIS_DIR.parent / "data"
if str(_DATA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_DATA_SCRIPTS))

from build_master import _MIN_BAND_SAMPLE  # noqa: E402  (B1 정책 단일 출처)
from camelot import to_camelot  # noqa: E402  (기존 모듈, 재구현 금지)

# repo_root 기준 상대 경로(데이터팀 산출물 6종 + 동결 상수)
REL_SONGS_FULL = "data/songs_full.csv"
REL_AUDIO_MAP = "data/audio_map.json"
REL_FEATURES = "data/song_features_with_proxies.csv"
REL_FULL_FEATS = "data/full_audio_features.csv"
REL_TEMPORAL = "data/temporal_intensity.csv"
REL_MASTER = "data/songs_master.csv"

APPEND_TARGETS = [REL_FEATURES, REL_FULL_FEATS, REL_TEMPORAL, REL_MASTER]
ALL_TARGETS = [REL_SONGS_FULL, REL_AUDIO_MAP] + APPEND_TARGETS


def band_eligibility(songs_full_rows: list[dict]) -> dict[str, bool]:
    """B1 정책(n>=10) — build_master._band_eligibility와 동일 규칙."""
    counts: dict[str, int] = {}
    for r in songs_full_rows:
        counts[r["band"]] = counts.get(r["band"], 0) + 1
    return {band: (n >= _MIN_BAND_SAMPLE) for band, n in counts.items()}


def assemble_master_row(master_idx: int, cand: dict, excerpt: dict, proxies: dict,
                        audio_entry: dict, energy_full: float,
                        intensity: dict, eligible: bool, shape: str,
                        audio_feats: dict | None = None) -> dict:
    """songs_master.csv 1행 조립. 포맷은 기존 빌드 스크립트들과 동일:
    tempo_excerpt·mode_score=r5, proxy=full float, energy_full='%.6f', i_*='%.5f'.

    2026-08-02: 9개 신규 오디오 지표 컬럼 추가 (report_final.md 기준):
    m3-mode, m4-lufs_integrated, m4-lra, m5-arousal_median, m6-valence_median,
    m7-danceability_norm, m8-acoustic_median, m9-instr_stem_ratio, m11-speech_median.
    audio_feats dict를 받으면 이들을 채우고, 없으면 None으로 둔다.

    shape는 상류(norms.compute_shape)가 우리 발췌 특징에서 직접 계산한 값을 받는다
    — 형제 audio_map의 신곡 엔트리에는 shape 키가 없어(2026-07-15 확인) audio_entry에
    더 이상 의존하지 않는다. energy(레거시, song_repo 비소비)는 있으면 쓰고 없으면 공란.

    master_idx는 **이 저장소 songs_master.csv 자체의 idx**로, `cand["idx"]`(형제
    songs_full.csv의 idx)와 별개다(merge()가 master 기존 최대값+1로 새로 부여 —
    "형제 idx = master idx" 가정이 깨지는 배경은 merge() 독스트링 참조). cand["idx"]는
    wav 캐시 파일명·형제 audio_map 조회 등 형제 저장소 쪽 참조에만 계속 쓰인다."""
    key = excerpt["key"]
    camelot = to_camelot(key)   # 매핑 누락 시 ValueError → 상위에서 롤백
    if audio_feats is None:
        audio_feats = {}
    row = {
        "idx": master_idx,
        "band": cand["band"],
        "song": cand["song"],
        "url": cand["url"],
        "video_id": cand["video_id"],
        "key": key,
        "camelot": camelot,
        "tempo_excerpt": excerpt["tempo_excerpt"],
        "energy_proxy": proxies["energy_proxy"],
        "mode_score": excerpt["mode_score"],
        "acousticness_proxy": proxies["acousticness_proxy"],
        "instrumentalness_proxy": proxies["instrumentalness_proxy"],
        "bpm": audio_entry["bpm"],
        "energy": audio_entry.get("energy", ""),
        "shape": shape,
        "eligible_band": eligible,
        "energy_full": f"{energy_full:.6f}",
        **{k: intensity[k] for k in
           ("i_mean", "i_std", "i_max", "i_min", "i_start", "i_end")},
        # 2026-08-02 신규: 9개 오디오 지표
        "m3-mode": audio_feats.get("m3-mode"),
        "m4-lufs_integrated": audio_feats.get("m4-lufs_integrated"),
        "m4-lra": audio_feats.get("m4-lra"),
        "m5-arousal_median": audio_feats.get("m5-arousal_median"),
        "m6-valence_median": audio_feats.get("m6-valence_median"),
        "m7-danceability_norm": audio_feats.get("m7-danceability_norm"),
        "m8-acoustic_median": audio_feats.get("m8-acoustic_median"),
        "m9-instr_stem_ratio": audio_feats.get("m9-instr_stem_ratio"),
        "m11-speech_median": audio_feats.get("m11-speech_median"),
    }
    return row


# ---------------------------------------------------------------------------
# 파일 기록(스냅샷·append·검증)
# ---------------------------------------------------------------------------

def _line_terminator(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw[:4096] else "\n"


def _append_rows(path: Path, rows: list[dict]) -> None:
    """CSV 끝에 행 append — 기존 헤더 순서·개행 방식 유지, 말미 개행 보정."""
    raw = path.read_bytes()
    term = _line_terminator(raw)
    with path.open(encoding="utf-8", newline="") as f:
        fieldnames = csv.DictReader(f).fieldnames
    if fieldnames is None:
        raise ValueError(f"헤더 없는 CSV: {path}")

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator=term)
    for r in rows:
        writer.writerow(r)

    out = buf.getvalue().encode("utf-8")
    with path.open("ab") as f:
        if raw and not raw.endswith(b"\n"):
            f.write(term.encode())
        f.write(out)


def merge(repo_root: Path, landed: list[dict],
          sorter_songs_full: bytes, sorter_audio_map: bytes) -> None:
    """landed 곡 전체를 data/에 반영. 실패 시 전 파일 스냅샷 복원 후 재raise.

    landed 항목 스키마(run_autoloader가 조립):
      cand(idx/band/song/url/video_id), excerpt(원시), proxies, full_feats(원시+extract_sec),
      audio_entry(bpm, +구형식이면 energy), shape(str, norms.compute_shape 산출),
      energy_full(float), intensity(i_* 문자열), eligible(bool)

    ⚠️ **cand["idx"]는 형제 songs_full.csv의 idx이지 이 저장소 songs_master.csv의
    idx가 아니다.** 예전에는 둘을 동일시해 cand["idx"]를 master에 그대로 썼는데,
    이는 형제 저장소가 "매번 끝에만 append"하는 한에서만 우연히 안전했다. 형제 측
    build_manifest.py는 곡 추가 시 yaml 파일명 알파벳순으로 songs_full.csv 전체를
    재정렬(전역 idx 재부여)하므로, 밴드 yaml 중간에 대량으로 곡이 삽입되면(예:
    2026-07-26 mutype 38곡 백필) 그 뒤에 오는 밴드들의 idx가 통째로 밀린다 — 그
    "새" idx가 master에 이미 존재하는 완전히 다른 곡의(과거에 부여된) idx와
    숫자만 우연히 겹칠 수 있다(실제 충돌 사례 확인됨). 그래서 이 함수는 master에
    쓸 idx를 **master 자신의 기존 최대값+1로 독립적으로 새로 부여**한다 — 형제
    쪽 idx가 앞으로 몇 번을 재정렬되든 master의 idx 공간은 영향받지 않는다.
    cand["idx"](형제 idx)는 wav 캐시 파일명·형제 audio_map 조회 등 형제 저장소
    참조에는 계속 그대로 쓰인다(그쪽은 원래도 위치 기반이라 손댈 필요 없음).
    """
    paths = {rel: repo_root / rel for rel in ALL_TARGETS}
    snapshot = {p: p.read_bytes() for p in paths.values() if p.exists()}

    try:
        master_before = _read_rows(paths[REL_MASTER])

        # master 자체 idx를 독립 부여(형제 idx와 무관, landed 순서대로 순차 채번)
        next_idx = max((int(m["idx"]) for m in master_before), default=-1) + 1
        for s in landed:
            s["master_idx"] = next_idx
            next_idx += 1

        _pre_checks(master_before, landed)

        # ① mirror: 형제 origin/main 바이트 그대로
        paths[REL_SONGS_FULL].write_bytes(sorter_songs_full)
        paths[REL_AUDIO_MAP].write_bytes(sorter_audio_map)

        # ② eligible 재계산(신곡 포함) — 기존 행 무변동 검증
        songs_full_rows = _read_rows(paths[REL_SONGS_FULL])
        elig = band_eligibility(songs_full_rows)
        for m in master_before:
            stored = str(m["eligible_band"]).strip().lower() == "true"
            if elig.get(m["band"], stored) != stored:
                raise AssertionError(
                    f"기존 행 eligible_band 변동 감지(band={m['band']}) — "
                    "정책 검토 필요, 자동 반영 중단")

        # ③ append 4종(idx는 전부 master_idx로 통일 — 네 파일이 idx로 조인되므로)
        _append_rows(paths[REL_FEATURES], [
            {"band": s["cand"]["band"], "idx": s["master_idx"],
             "song": s["cand"]["song"], **s["excerpt"], **s["proxies"]}
            for s in landed])
        _append_rows(paths[REL_FULL_FEATS], [
            {"idx": s["master_idx"], "band": s["cand"]["band"],
             "song": s["cand"]["song"], "error": "", **s["full_feats"]}
            for s in landed])
        _append_rows(paths[REL_TEMPORAL], [
            {"idx": s["master_idx"], "band": s["cand"]["band"],
             "song": s["cand"]["song"], **s["intensity"]}
            for s in landed])
        _append_rows(paths[REL_MASTER], [
            assemble_master_row(s["master_idx"], s["cand"], s["excerpt"], s["proxies"],
                                s["audio_entry"], s["energy_full"],
                                s["intensity"], elig[s["cand"]["band"]],
                                s["shape"])
            for s in landed])

        _post_checks(paths, snapshot, master_before, landed)

    except Exception:
        for p, b in snapshot.items():
            p.write_bytes(b)
        raise


def _read_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


I_FIELDS = ["i_mean", "i_std", "i_max", "i_min", "i_start", "i_end"]


def patch_intensity_rows(repo_root: Path, updates: dict[int, dict[str, str]]) -> None:
    """soft-run이 밴드 평균으로 임시 대체했던 i_* 컬럼을, 정식 동결 norm이 준비된
    이후의 일반 run에서 실측값으로 되짚어 갱신한다(백필).

    이 함수는 `merge()`의 "기존 행 바이트 불변" 불변식에 대한 **의도된 예외**다 —
    대상은 오직 이전에 provisional로 표시된 행의 i_* 6컬럼뿐이고, idx/band/song 등
    나머지 모든 필드·모든 다른 행은 그대로 둔다. songs_master.csv와
    temporal_intensity.csv 둘 다 갱신하며, 실패 시 두 파일 전체를 스냅샷 복원한다.

    updates: {idx: {"i_mean": "...", ...}} — norms.aggregate_intensity() 산출 그대로.
    """
    if not updates:
        return
    paths = {REL_MASTER: repo_root / REL_MASTER, REL_TEMPORAL: repo_root / REL_TEMPORAL}
    snapshot = {p: p.read_bytes() for p in paths.values()}
    try:
        for rel, p in paths.items():
            rows = _read_rows(p)
            with p.open(encoding="utf-8", newline="") as f:
                fieldnames = csv.DictReader(f).fieldnames
            term = _line_terminator(snapshot[p])
            patched = 0
            for r in rows:
                u = updates.get(int(r["idx"]))
                if u is None:
                    continue
                r.update({f: u[f] for f in I_FIELDS})
                patched += 1
            if patched != len(updates):
                found = {int(r["idx"]) for r in rows} & set(updates)
                missing = set(updates) - found
                raise AssertionError(f"{rel}: idx 못 찾음(백필 대상 아님?): {sorted(missing)}")
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=fieldnames, lineterminator=term)
            writer.writeheader()
            writer.writerows(rows)
            p.write_bytes(buf.getvalue().encode("utf-8"))
    except Exception:
        for p, b in snapshot.items():
            p.write_bytes(b)
        raise


def _pre_checks(master_before: list[dict], landed: list[dict]) -> None:
    known_vid = {(m.get("video_id") or "").strip() for m in master_before}
    known_idx = {int(m["idx"]) for m in master_before}
    seen_vid: set[str] = set()
    seen_idx: set[int] = set()
    for s in landed:
        c = s["cand"]
        vid = c["video_id"]
        if len(vid) != 11:
            raise AssertionError(f"video_id 11자 아님: {c}")
        if vid in known_vid or vid in seen_vid:
            raise AssertionError(f"video_id 중복(이미 반영됨?): {c}")
        midx = s["master_idx"]
        if midx in known_idx or midx in seen_idx:
            # master_idx는 merge()가 기존 최대값+1로 새로 채번하므로 이론상 불가능한
            # 경로다 — 도달하면 merge() 호출 전에 landed가 변조됐다는 뜻(진짜 버그).
            raise AssertionError(f"master_idx 충돌(내부 채번 버그 의심): {c}, master_idx={midx}")
        seen_vid.add(vid)
        seen_idx.add(midx)


def _post_checks(paths: dict[str, Path], snapshot: dict[Path, bytes],
                 master_before: list[dict], landed: list[dict]) -> None:
    # append 파일은 기존 내용의 순수 연장이어야 함(기존 행 바이트 불변).
    # 말미 개행 보정(term 삽입)이 있어도 old 자체는 항상 새 내용의 prefix다.
    for rel in APPEND_TARGETS:
        p = paths[rel]
        old = snapshot.get(p, b"")
        new = p.read_bytes()
        if not new.startswith(old):
            raise AssertionError(f"append가 기존 내용을 변경함: {rel}")

    master_after = _read_rows(paths[REL_MASTER])
    if len(master_after) != len(master_before) + len(landed):
        raise AssertionError(
            f"master 행 수 불일치: {len(master_after)} != "
            f"{len(master_before)} + {len(landed)}")

    idxs = [int(r["idx"]) for r in master_after]
    if len(set(idxs)) != len(idxs):
        raise AssertionError("master idx 중복 발생")
    vids = [(r.get("video_id") or "").strip() for r in master_after]
    if len(set(vids)) != len(vids):
        raise AssertionError("master video_id 중복 발생")

    # 신규 행이 song_repo가 요구하는 타입으로 파싱되는지(엔진 소비 계약)
    new_by_idx = {int(r["idx"]): r for r in master_after[len(master_before):]}
    for s in landed:
        r = new_by_idx[int(s["master_idx"])]
        float(r["mode_score"]); float(r["acousticness_proxy"])
        float(r["energy_full"])
        for col in ("i_mean", "i_std", "i_max", "i_min", "i_start", "i_end"):
            float(r[col])
        if not r["camelot"].strip():
            raise AssertionError(f"camelot 공란: idx={r['idx']}")
        if str(r["eligible_band"]) not in ("True", "False"):
            raise AssertionError(f"eligible_band 형식 오류: {r['eligible_band']!r}")
