#!/usr/bin/env python3
"""Fetch bestdori official BPM for catalog songs (report/01 §6.2-2).

1. all.5.json에서 곡 목록을 받아 bandId + 정규화 제목으로 카탈로그와 매칭.
2. 매칭된 곡만 /api/songs/{id}.json을 조회(캐시, idempotent)해 bpm 세그먼트에서
   지배 BPM(구간 길이 가중 최빈값)을 추출한다.

게임 미수록 밴드(mugendai_mutype 등)와 미구현 신곡은 매칭 실패로 자연 제외된다.
"""
import json
import re
import sys
import time
import unicodedata
import urllib.request

import pandas as pd

from config import (BPM_SELECTED_CSV, BESTDORI_BPM_CSV, BESTDORI_CACHE_DIR,
                    BESTDORI_ALL_URL, BESTDORI_SONG_URL, FETCH_SLEEP_SEC, BAND_ID)


def fetch_json(url, cache_path):
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": "bandori-playlist-maker research (personal)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(FETCH_SLEEP_SEC)
    return data


def norm_title(s):
    if s is None:
        return None
    s = unicodedata.normalize("NFKC", str(s)).casefold()
    s = s.replace("〜", "~")  # wave dash 〜 -> ~ (NFKC가 전각 ～만 ~로 접음)
    return "".join(s.split())  # 공백류 제거


_COVER_RE = re.compile(r"\s*\((cover)\)\s*$", re.IGNORECASE)
_TRAIL_PAREN_RE = re.compile(r"\s*[(（][^()（）]*[)）]\s*$")


def title_keys(raw_title):
    """매칭 시도 순서대로 정규화 키 목록(중복 제거)을 만든다.

    1. 원제목  2. '(Cover)' 접미사 제거  3. 말미 괄호구(버전 표기 등) 제거
    """
    t1 = str(raw_title)
    t2 = _COVER_RE.sub("", t1)
    t3 = _TRAIL_PAREN_RE.sub("", t2)
    keys = []
    for t in (t1, t2, t3):
        k = norm_title(t)
        if k and k not in keys:
            keys.append(k)
    return keys


def dominant_bpm(song_json):
    """bpm 세그먼트(난이도 '0' 우선)에서 구간 길이 가중 지배 BPM을 뽑는다."""
    bpm_field = song_json.get("bpm") or {}
    key = "0" if "0" in bpm_field else (sorted(bpm_field)[0] if bpm_field else None)
    if key is None:
        return None
    segs = bpm_field[key]
    weight = {}
    for seg in segs:
        dur = float(seg["end"]) - float(seg["start"])
        weight[float(seg["bpm"])] = weight.get(float(seg["bpm"]), 0.0) + dur
    total = sum(weight.values()) or 1.0
    bpm, dur = max(weight.items(), key=lambda kv: kv[1])
    return {
        "official_bpm": bpm,
        "official_bpm_min": min(weight),
        "official_bpm_max": max(weight),
        "n_unique_bpm": len(weight),
        "dominant_coverage": dur / total,
    }


def main():
    BESTDORI_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    catalog = pd.read_csv(BPM_SELECTED_CSV)
    allsongs = fetch_json(BESTDORI_ALL_URL, BESTDORI_CACHE_DIR / "all.5.json")

    # 밴드별/전역 제목 인덱스; musicTitle은 로케일 배열이라 non-null 전부 인덱싱
    by_band, by_title = {}, {}
    for sid, meta in allsongs.items():
        for title in (meta.get("musicTitle") or []):
            k = norm_title(title)
            if k is None:
                continue
            by_band.setdefault((meta.get("bandId"), k), set()).add(int(sid))
            by_title.setdefault(k, set()).add(int(sid))

    def find_match(band_id, raw_title):
        keys = title_keys(raw_title)
        for key in keys:  # 1순위: 밴드 일치
            sids = by_band.get((band_id, key))
            if sids:
                return min(sids), "band+title"
        for key in keys:  # 2순위: 전역 유일 제목(명의 차이·커버 수록 대응)
            sids = by_title.get(key)
            if sids and len(sids) == 1:
                return next(iter(sids)), "title-unique"
        return None, None

    rows, unmatched = [], []
    for _, row in catalog.iterrows():
        band_id = BAND_ID.get(row["band"])
        if band_id is None:
            unmatched.append((row["tag"], row["song"], "band not in game"))
            continue
        sid, method = find_match(band_id, row["song"])
        if sid is None:
            unmatched.append((row["tag"], row["song"], "title not found"))
            continue
        song_json = fetch_json(BESTDORI_SONG_URL.format(id=sid), BESTDORI_CACHE_DIR / f"{sid}.json")
        info = dominant_bpm(song_json)
        if info is None:
            unmatched.append((row["tag"], row["song"], "no bpm field"))
            continue
        rows.append({"idx": row["idx"], "tag": row["tag"], "bestdori_id": sid,
                     "match_method": method, **info})

    res = pd.DataFrame(rows)
    res.to_csv(BESTDORI_BPM_CSV, index=False)
    print(f"matched: {len(res)} / {len(catalog)}  (unmatched: {len(unmatched)})")
    reasons = pd.Series([r for _, _, r in unmatched])
    print(reasons.value_counts().to_string())
    with open(BESTDORI_CACHE_DIR / "unmatched.txt", "w", encoding="utf-8") as f:
        for tag, song, reason in unmatched:
            f.write(f"{tag}\t{song}\t{reason}\n")
    print(f"unmatched list -> {BESTDORI_CACHE_DIR / 'unmatched.txt'}")


if __name__ == "__main__":
    main()
