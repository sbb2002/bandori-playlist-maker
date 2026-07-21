# KS_PROFILES `np.roll` 부호 버그 발견 — 조성(`key`) 라벨 전체 재산출 필요

morfonica 20곡이 전부 `key_proxies=Amin`으로 몰려 있는 걸 발견하고 조성 검증에 들어갔다.
Spotify Web API(tunebat.com 경유) 교차검증에서 실제 불일치를 확인했고, 원인을 추적하다
`estimate_key()`가 참조하는 `KS_PROFILES` 딕셔너리 생성 코드에서 **결정론적 라벨링 버그**를
찾았다. 오디오 재처리는 이 세션에서 못 했다 — 서브 로컬 환경이라 원본 오디오(661곡)가 이
기기에 없음(`config.py`의 `AUDIO_DIR`가 가리키는 형제 프로젝트 경로가 로컬에 없음). 코드
수정만 하고 재산출은 메인 기기로 인계한다.

## 1. 배경 — 왜 조사했나

`data/songs_master.csv`에서 morfonica 밴드만 필터링해보니 57곡 중 19곡(33%)이 `key=Amin`
이었다 — 전체 카탈로그 평균(37/661≈5.6%)보다 압도적으로 높은 비율. `report/04`가 이미
morfonica를 "어두운(단조 우세) 밴드"로 확인한 바 있어 단순히 단조가 많다는 것 자체는
이상하지 않지만, **정확히 "A minor"라는 특정 조성 하나에 쏠려 있는 건** 별개 의심 지점이었다.

## 2. 1차 검증 — Spotify Web API(tunebat.com) 교차대조

Amin으로 표시된 20곡 중 Spotify 카탈로그에 등록된 7곡을 tunebat.com에서 대조했다(tunebat의
검색 결과 key/BPM은 Spotify Web API의 Audio Features 값 — 우리와 독립적인 제3자 산출값).

| 곡 | 우리 `key`(`key_proxies`) | tunebat(Spotify) | 판정 |
|---|---|---|---|
| 誓いのWingbeat | Amin | A minor | ✅ 일치 |
| 輪舞-revolution (Cover) | Amin | A minor | ✅ 일치 |
| flame of hope | Amin | G major | ❌ 불일치 |
| 寄る辺のSunny, Sunny | Amin | F major | ❌ 불일치 |
| Secret Dawn | Amin | B♭ major | ❌ 불일치 |
| Angel's Ladder | Amin | B♭ major | ❌ 불일치 |
| メリッサ (Cover) | Amin | A♭ major | ❌ 불일치 (원곡 Porno Graffitti도 G major) |

**7곡 중 5곡(71%)이 불일치**, 전부 "실제는 장조인데 우리는 단조(Amin)로 오검출"하는
방향으로만 틀렸다. mode_score가 0에 가까운(확신 낮은) 곡일수록 불일치했다
(Secret Dawn −0.009, Angel's Ladder −0.031 등). 나머지 13곡은 Spotify 카탈로그 자체에
없어 이 방법으로 검증 불가(비공식/스트리밍 미배포 추정).

## 3. 2차 검증 — 코드 레벨 원인 확인

`topic/audio_feats_analysis/src/method-1/config.py`의 `KS_PROFILES` 생성부:

```python
# 수정 전
KS_PROFILES[f"{pc}maj"] = np.roll(_KS_MAJOR, -pc_idx)
KS_PROFILES[f"{pc}min"] = np.roll(_KS_MINOR, -pc_idx)
```

`np.roll(a, -p)`는 `result[i] = a[(i+p) mod 12]`로 계산된다. Krumhansl-Kessler 프로파일은
인덱스 0이 "토닉(으뜸음) 가중치"(최댓값)이므로, 조성 `X`(피치클래스 인덱스 `p`)의 프로파일은
`result[p] = a[0]`이 되어야 정상 — 즉 `np.roll(a, +p)`가 맞다. 부호가 반대라 **토닉 가중치가
라벨이 가리키는 피치클래스가 아니라 `(12-p) mod 12` 위치에 붙는다.**

노이즈 없는 이상적 크로마로 직접 시뮬레이션해서 확인:

```
Gmaj  -> Fmaj   로 오검출 (corr=1.000, 완벽한 상관 — 신호 노이즈 문제가 아니라 라벨 자체가 틀림)
D#min -> Amin   로 오검출
Amin  -> D#min  로 오검출
C, F#만 우연히 정상(자기 자신과 대칭인 두 조성)
```

`np.roll(_KS_MAJOR, pc_idx)` / `np.roll(_KS_MINOR, pc_idx)`로 부호를 고친 뒤 재검증하면
12개 조성(장/단조 총 24개 프로파일) 전부 라벨과 실제 피크 위치가 일치한다(완료, §5).

## 4. 이 버그가 설명하는 것과 설명하지 못하는 것

**설명함**: 같은 모드(장조↔장조, 단조↔단조) 내에서 라벨이 뒤바뀌는 것. 완전히 결정론적이라
오디오가 아무리 깨끗해도 100% 재현된다.

**설명 못함**: §2에서 발견한 "장조 곡이 Amin(단조)으로 오검출"되는 패턴. 버그 시뮬레이션상
장조는 항상 다른 장조로만, 단조는 항상 다른 단조로만 잘못 라벨링되고 — G장조가 Amin으로
잘못 나올 경로가 수학적으로 없다(부록: G장조는 버그가 있어도 F장조로만 오검출됨).

**결론**: 최소 **두 개의 독립된 문제**가 겹쳐 있다.
1. **확정된 코드 버그**(§3) — 100% 재현 가능, 수정 완료.
2. **장/단조 자체의 혼동** — K-S 상관계수 방식의 고질적 약점(relative major/minor가 피치클래스
   집합을 공유해 원래 상관계수가 붙어있음) + `report/05`가 이미 지적한 실제 오디오 신호의
   노이즈(보컬/타악기 프레임 혼입 등)가 결합된 것으로 추정. 버그 수정만으로는 해소 안 될 수
   있다 — §6 참조.

## 5. 수정 사항

`topic/audio_feats_analysis/src/method-1/config.py`:
```python
KS_PROFILES[f"{pc}maj"] = np.roll(_KS_MAJOR, pc_idx)   # was: -pc_idx
KS_PROFILES[f"{pc}min"] = np.roll(_KS_MINOR, pc_idx)   # was: -pc_idx
```
수정 후 24개 프로파일 전부 라벨-피크 일치 재확인 완료(이상적 크로마 기준, corr=1.000).

**미해결**: `key_proxies`/`mode_score_proxies`의 출처인 `data/song_features_with_proxies.csv`는
이 repo에 생성 스크립트가 없는 외부 입력 파일이다(레거시 `energy_proxy`·`acousticness_proxy`
등 발췌 기반 지표와 같은 파일에 들어있음 — `topic/vector_embedding/report/02` §3 참조).
이번 조사에서 확인한 57곡 전부 `key`와 `key_proxies`가 정확히 일치했는데, 이게 (a) 같은
버그를 공유하는 별도 계산인지 (b) 애초에 같은 값을 복사한 건지 원인을 못 밝혔다 — 메인
기기에서 이 파일의 출처를 먼저 확인할 것.

## 6. 다음 세션 인수인계 (메인 기기에서 할 일)

1. **661곡 전체 재산출**: `topic/audio_feats_analysis/src/method-1/extract_features.py`를
   수정된 `config.py`로 재실행 → `est_key`/`key` 컬럼 갱신 → `out/audio_feats.csv`,
   `data/songs_master.csv` 재병합. `key_proxies` 출처(§5 미해결)도 먼저 확인 후 필요시 같이
   처리.
2. **재산출 후 재검증**: §2와 동일한 방식으로 tunebat 교차대조를 더 넓은 표본(morfonica
   외 밴드 포함)으로 재실행 — 버그 수정으로 불일치율이 실제로 줄었는지 확인.
3. **잔여 장/단조 혼동 조사(§4-2)**: 버그 수정 후에도 불일치가 남으면, Essentia
   (`KeyExtractor`, HPCP 기반 — MTG 오픈소스, AGPL-3.0)를 **로컬 오디오에 직접 돌려서**
   비교할 것. 단 라이선스 위생을 위해:
   - Essentia를 이 repo 코드에 직접 import(라이브러리 링크)하지 말고, standalone 바이너리
     (`essentia_streaming_extractor_music`)를 **subprocess로 호출**해서 결과 파일만 읽는 방식
     사용 (결합저작물 논쟁 회피).
   - repo에는 **산출 CSV만 커밋**, Essentia 호출 스크립트나 Bushiroad 원곡 오디오는 커밋
     금지(오디오는 이미 `.gitignore`로 걸러지는 기존 관행 그대로 유지).
4. `mode_score`(연속값) 자체는 이번 버그의 직접 영향권 밖일 가능성이 있다 —
   `topic/vector_embedding/report/02` §2b가 별도 ground-truth(65행 라벨)로 방향성을
   검증했고 그때도 이 버그는 존재했었다. 다만 그 검증은 "장/단조 분리가 방향은 맞다"까지만
   확인했지 "개별 곡 라벨이 정확하다"는 아니었으므로, 재산출 후 같은 ground-truth로 재검증
   권장.

## 7. 산출물
- 코드 수정: `topic/audio_feats_analysis/src/method-1/config.py` (`KS_PROFILES` 생성부,
  `np.roll` 부호 수정)
- 이 세션에서 재현용으로 쓴 검증 스니펫은 파일로 저장하지 않음 — §3/§5의 시뮬레이션 로직
  재현 시 이 리포트 코드 블록 참조
- tunebat 교차대조 원본 스크래치: `scratch_morfonica_amin.txt`(repo 루트, 커밋 대상 아님)
