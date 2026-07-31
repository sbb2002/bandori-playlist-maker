# 음원 피처 11종(Spotify/Echo Nest Audio Features) 산출 방법론

> **목적**: `README.md`가 정한 원칙(기존 코드·공식 재참조 금지, 전곡 오디오 기준, ground truth
> 없는 임의 가중치 금지) 아래 `energy`·`valence`·`danceability`·`acousticness`·`speechiness`·
> `instrumentalness`·`liveness`·`loudness`·`mode`·`key`·`tempo` 11종을 어떤 방법으로
> 산출할지 확정한다. 이 문서는 **산출 계획**이며, 실행·검증 결과는 `report/`에 별도로 남긴다.
>
> **개정(2026-07-31, 2판)**: 설계 검토 반영 — 실행환경 확정(WSL2+GPU), energy·valence 1차
> 후보를 연속값 arousal-valence 회귀로 교체, speechiness를 보컬 스템 기반으로 변경(템포 교락),
> key를 윈도우 다수결로 변경(전조 문제), GT 과적합 방지 요건·분포 퇴화 탈출 조건 신설,
> 시계열 우선 산출 원칙(동적 피처는 요약통계 세트 + GT로 대표 스칼라 선택) 추가, 요약통계
> 세트를 전 스칼라 피처 일괄 산출로 통일(key·mode·tempo 제외, loudness는 표준 LRA).

## 실행환경 (확정)

- **메인 로컬에서 실행**: 전곡 오디오 캐시 보유, GPU 사용 가능, **보컬/악기 분리 스템 보유**
  (speechiness·instrumentalness에서 활용 — 신규 소스분리 실행 불필요).
- **Essentia·essentia-tensorflow·madmom은 Windows 미지원/빌드 곤란** → **WSL2에 Linux 환경을
  구축해 실행**한다. madmom은 PyPI 0.16.1(2018)이 numpy 1.24+/Python 3.10+와 비호환이므로
  GitHub master에서 설치.
- 일부 도구(PANNs, pyloudnorm)는 Windows 네이티브도 가능하나, 재현성을 위해 **전 피처를 WSL
  단일 환경에서 실행**하고 패키지 버전·모델 체크포인트 해시를 고정 기록한다.

## 요약

| # | 피쳐 | 1차 산출 방법 | 방식 | Proxy |
|---|---|---|---|---|
| 1 | tempo | 온셋 강도 자기상관 + 비트트래킹 (madmom `DBNBeatTracker`) + 옥타브 판정 정책 | 통계+ML | 아님 |
| 2 | key | **윈도우별** 크로마 vs Krumhansl-Schmuckler 템플릿 → 지속시간 가중 다수결 | 통계적 | 아님 |
| 3 | mode | key 산출의 부산물(장/단조) | 통계적 | 아님 |
| 4 | loudness | ITU-R BS.1770 통합 라우드니스(`pyloudnorm`) | 통계적/표준 | 아님 |
| 5 | energy | Essentia **emoMusic/DEAM 학습 arousal 연속 회귀** → 자체 GT로 캘리브레이션 검증 | ML | 경(輕) Proxy |
| 6 | valence | Essentia **emoMusic/DEAM 학습 valence 연속 회귀** → 자체 GT로 캘리브레이션 검증 | ML | 경(輕) Proxy |
| 7 | danceability | Essentia `Danceability`(DFA 지수) | 통계적 | 아님 |
| 8 | acousticness | Essentia `mood_acoustic` 분류기 | ML | 경(輕) Proxy |
| 9 | instrumentalness | Essentia `voice_instrumental` 분류기 + 보유 스템 에너지비 교차검증 | ML | 경(輕) Proxy |
| 10 | liveness | PANNs(AudioSet) Crowd/Applause/Cheering 확률 | ML | **Proxy** |
| 11 | speechiness | Scheirer-Slaney 4Hz 변조 에너지를 **보컬 스템**에 적용 | 통계적 | 아님(스템 품질 의존) |

## 상세

| # | 피쳐 | 방식 | 산출 공식 / 모델 | Proxy 여부 |
|---|---|---|---|---|
| 1 | **tempo** | 통계적(고전 MIR) | 온셋 강도 o(t) = Σ_f max(0, \|X(t,f)\|−\|X(t−1,f)\|)(스펙트럴 플럭스) → 자기상관 R(τ)=Σ_t o(t)o(t+τ) 피크에서 BPM 후보 산출 → Ellis(2007) 동적계획법 비트트래킹으로 정제 | 아님 — 원 목적과 정확히 일치하는 고전 알고리즘 |
| | | ML 대체(정확도↑) | **madmom** `DBNBeatTracker`(RNN 기반 사전학습). **주의**: 기본 탐지 범위가 약 55–215BPM이라 이 카탈로그의 고속곡(215BPM+)이 반절로 접힐 수 있음 → min/max BPM 설정 및 **옥타브(반절/배속) 판정 정책**(비트 간격 중앙값 기준 등)을 파일럿에서 확정. 곡 중간 하프타임 구간이 있는 곡의 대표값 집계 방식(전곡 비트 간격 중앙값)도 사전 등록 | 아님(진짜 목적에 맞는 오픈 모델) |
| 2 | **key** | 통계적 | 크로마 c(t)∈ℝ¹²(CQT) → **10–20초 윈도우별** 평균 크로마에 Krumhansl-Schmuckler 매칭(template = Krumhansl-Kessler(1982) 24개 프로파일) → **지속시간 가중 다수결**로 대표 키 + **전조 플래그** 기록. 전곡 단일 평균은 기각 — 이 장르는 마지막 후렴 반음~온음 상행 전조가 빈발해 전곡 평균 크로마가 두 키의 혼합이 됨 | 아님, **전곡 기준**(45초 발췌 금지) 유지 |
| | | 교차검증 | **Essentia** `KeyExtractor`(HPCP 기반 별도 알고리즘). 집계 시 **"키 불일치"와 "모드만 불일치"를 구분** 기록 — K-S의 고전적 오류 패턴이 관계장/단조 혼동이므로 mode(3) 신뢰도 판단에 직결 | 아님 |
| 3 | **mode** | 통계적 | 위 key 산출의 부산물 — 매칭된 template(k,m)의 m(장조/단조). 신뢰도는 key 교차검증의 "모드만 불일치" 비율로 평가 | 아님 |
| 4 | **loudness** | 통계적/표준 | ITU-R BS.1770 통합 라우드니스(LUFS): K-weighting 필터 → 채널합산 평균제곱 → 게이팅(절대 −70LUFS, 상대 −10LU) → 적분. **pyloudnorm**으로 그대로 계산. 병행 산출: short-term loudness(3초) 시계열 + EBU R128 **LRA**(변동폭). **선행 확인**: 소스 음원의 마스터링·인코딩 일관성(플랫폼 라우드니스 정규화가 이미 적용된 파일 혼입 여부) | 아님 — 국제표준 구현체 |
| 5 | **energy** | ML(1차 후보) | **Essentia** emoMusic/DEAM 데이터셋으로 학습된 **arousal 연속 회귀 모델**(MusiCNN 임베딩 기반, essentia-tensorflow 제공). 처음부터 연속값 출력이라 이진 분류기 확률차보다 연속 피처 대용으로 적합. **동적 피처** — 윈도우 시계열로 산출해 요약통계 세트(중앙값·p10·p90·표준편차)를 남기고, 대표 스칼라는 GT와의 순위 상관으로 선택. 자체 GT의 역할은 가중치 학습이 아니라 **캘리브레이션 검증**(GT와의 단조성 확인) | **경 Proxy** — arousal은 energy와 개념적으로 근접하나 동일 정의는 아님. 학습 데이터가 서구권 일반 음악이므로 이 장르 일반화는 GT 검증 필수 |
| | | 통계적 대체 | arousal 회귀가 GT 검증에서 실패할 때만: loudness(4) + spectral contrast z + onset rate z + 다이나믹레인지(EBU R128 LRA 우선, 또는 RMS p95−p5) z 결합, **가중치는 자체 GT로 회귀 학습**(임의 균등합 금지). 아래 "GT 설계 요건"의 과적합 방지 조항 적용 필수 | 아님(통계 결합), 단 GT 학습 전엔 미완성 |
| 6 | **valence** | ML(1차 후보) | **Essentia** emoMusic/DEAM 학습 **valence 연속 회귀 모델**(위 arousal과 동일 모델 계열 — 한 번의 추론으로 energy·valence 동시 커버). **동적 피처** — energy와 동일하게 요약통계 세트 산출 후 대표 스칼라를 GT로 선택. 자체 GT로 캘리브레이션 검증 | **경 Proxy** — 연속 valence 회귀라는 점에서 목적 일치, 학습 도메인 차이만 검증 필요 |
| | | ML 대체(격하) | `mood_happy`/`mood_sad` 분류기 확률차 — **이진 분류기 출력이라 0/1 근처로 포화**되는 경향이 있어 연속 valence 대용으로 질이 낮음(1차 후보에서 격하한 사유) | **Proxy** |
| | | 통계적 보조 | mode(3) 비율 + tempo(1) + spectral centroid(밝기) 결합 회귀, GT로 가중치 학습. `mode_score` 단독 사용은 명시적으로 금지(이전 결함 반복) | 아님(통계 결합) |
| 7 | **danceability** | 통계적(1차 후보) | **Essentia** `Danceability` 알고리즘 — 에너지 시계열의 DFA(Detrended Fluctuation Analysis) 지수 α(낮을수록 리듬 규칙적=danceable), 결정론적, ML 아님. 원시 α는 0–1이 아니므로 아래 "정규화 규약" 적용 | 아님 |
| | | ML 대체 | **Essentia** 사전학습 `danceability` 분류기(MusiCNN 임베딩 + transfer learning) | **Proxy** — Spotify 정의를 직접 학습한 모델이 아니라 별도 라벨셋 기반 |
| 8 | **acousticness** | ML | **Essentia** 사전학습 `mood_acoustic` 분류기(acoustic/non_acoustic 확률). 카탈로그가 밴드 사운드 위주라 분포 퇴화 예상 — 아래 "분포 퇴화 탈출 조건" 적용 | **경(輕) Proxy** — 개념은 거의 일치하나 Spotify 원 모델·라벨셋과는 다름 |
| 9 | **instrumentalness** | ML | **Essentia** 사전학습 `voice_instrumental` 분류기(voice/instrumental 확률) | **경 Proxy** — 개념 일치, 출처 모델 다름 |
| | | 통계적 교차검증 | **보유 스템 활용**(신규 소스분리 실행 불필요, 비용 0): instrumentalness = 1 − (vocal_stem_energy / total_energy). 분류기와의 순위 상관으로 상호 검증 | **Proxy** — 분리 결과의 재해석 |
| 10 | **liveness** | ML | **PANNs**(Kong et al. 2020, AudioSet 527클래스 CNN14, 사전학습 오픈) — "Crowd"/"Applause"/"Cheering" 클래스 확률 평균. **오탐 주의**: 곡 내 함성 이펙트·갱보컬("Hey!" 등)이 Crowd/Applause로 잡힐 수 있음 → 파일럿에서 상위 검출 곡 청취 대조 필수 | **Proxy(명확)** — 관객 소음 이벤트 탐지지 "라이브 공연일 확률" 자체가 아님 |
| | | 통계적 보조 | 트랙 전체 노이즈플로어 광대역 에너지 + 잔향 꼬리 길이(RT60 추정) | **Proxy**(공연장 잔향 근사) |
| 11 | **speechiness** | 통계적(1차 후보) | Scheirer-Slaney(1997) 4Hz 변조 에너지를 **보컬 스템**(보유)에 적용: modulation_energy = bandpass(envelope_spectrum, 3–4Hz) 에너지 비. **풀믹스 적용 금지** — 4분음표 주기가 180BPM=3Hz, 240BPM=4Hz로 드럼 리듬이 탐지 대역과 정면 교락하며, 이 카탈로그는 고속곡이 많아 풀믹스에선 사실상 템포를 측정하게 됨 | 아님 — 개념 자체를 겨냥한 고전 공식(단 스템 분리 품질에 의존) |
| | | ML 교차검증 | **inaSpeechSegmenter**(INA, 사전학습 음성/음악/잡음 분류기) 또는 **pyannote** VAD — 프레임별 speech 확률의 트랙 평균 | **Proxy** — 이진 speech/non-speech만 주고, 랩·팟캐스트류 세분화(원 정의)는 없음 |

## 산출 공통 규약

- **전곡 오디오** 기준, 45초 발췌 금지. 시작/끝 무음 트리밍 정책(임계 dBFS)을 사전 고정하고
  전 피처에 동일 적용. 단 "전곡 기준"은 **입력 커버리지** 원칙이지 "전곡을 스칼라 하나로
  뭉갠다"는 뜻이 아니다 — 아래 시계열 우선 원칙 참조.
- **시계열 우선 산출**: 모든 피처는 윈도우/패치 단위 **시계열로 먼저 산출해 그대로 저장**하고,
  트랙 대표값은 시계열의 후처리(집계)로만 만든다. 집계 방식은 재추론 없이 언제든 바꿀 수 있는
  되돌리기 가능한 결정으로 남긴다.
- **요약통계 세트 일괄 산출**: 스칼라 시계열이 나오는 모든 피처(energy, valence,
  danceability, loudness, acousticness, instrumentalness, liveness, speechiness)는 동일한
  요약통계 세트 **중앙값·p10·p90·표준편차**를 일괄 산출한다 — 피처별 분기 없이 집계 경로
  하나로 통일. 원시 시계열도 저장하므로 다른 통계가 필요해지면 재추론 없이 재집계 가능.
  - **예외 — key·mode·tempo**: 범주형이거나 분위수가 무의미(BPM은 중앙값 하나로 충분) →
    지속시간 가중 다수결(key·mode)·비트 간격 중앙값(tempo) + 예외 플래그(전조·하프타임)로
    집계.
  - **loudness는 표준 준수로 해결**: 대표값은 통합 LUFS(전곡 게이팅 적분, 윈도우 평균 아님)
    를 표준 그대로 유지하고, 시계열은 BS.1770 **short-term loudness(3초)**, 변동폭은 EBU
    R128 **LRA(Loudness Range, ≈p95−p10)** — 요약통계 세트의 표준화판이 이미 존재하므로
    자체 발명 대신 표준을 쓴다.
- **정적 vs 동적 구분은 "선곡 엔진에 뭘 넣느냐"의 문제다** — 산출물은 전 피처 동일:
  - **정적**(곡 수준 속성 — key, mode, tempo, loudness, acousticness, instrumentalness,
    liveness, speechiness): 엔진 투입 기본 대표값 = 중앙값(loudness는 통합 LUFS). 정적
    피처의 std는 진단 지표로 활용 — 예: acousticness std가 큰 곡은 "어쿠스틱 인트로 →
    밴드 진입" 구조 신호이므로 분포 퇴화 점검·오탐 청취 대조 시 우선 청취 대상 선정에 사용.
  - **동적**(구간별 변동이 지각에 중요 — energy, valence, danceability): **엔진 투입용
    대표 스칼라는 GT 검증으로 선택**한다 — 어느 요약통계가 지각 평가(GT)와 순위 상관이
    가장 높은지로 결정하며, 판정 기준은 사전 등록(임의로 상위분위를 고르는 것 금지 —
    rms_p90 과적합의 교훈). 변동폭(p90−p10) 자체도 "다이나믹한 곡" 정보로서 별도 활용
    여지가 있음.
  - 구간 구조 분석(후렴 검출 등)은 요약통계로 부족함이 확인될 때만 추가한다.
- **패치 단위 모델의 집계**: MusiCNN 계열·PANNs는 수 초 패치 단위로 출력하므로 3–5분
  곡에서 패치 수십 개가 나옴 — 위 시계열 우선 원칙의 적용 대상. 평균은 조용한
  인트로/아웃트로에 희석되는 점 고려. 파일럿에서 후보 비교는 허용하되 정식 산출 전에 고정.
- **0–1 정규화**: 원시 스케일이 제각각(LUFS, DFA α, 회귀 출력, 확률)이므로 Spotify 호환
  0–1 스케일로의 매핑 방식(카탈로그 내 백분위 상대 정규화 vs 절대 매핑)을 피처별로 결정.
  이 선택은 선곡 엔진의 해석에 직접 영향을 주므로 정식 산출 전 확정.
- **재현성**: WSL 환경의 패키지 버전 잠금(requirements lock), 모델 체크포인트 해시, 랜덤
  시드 고정.

## Ground truth 설계 요건 (energy·valence)

- **이전 연구의 산출값·라벨은 GT로 쓰지 않는다** — 설계 결함(45초 발췌, 밴드 판별력 검증,
  임의 가중치)으로 결과값 자체를 신뢰할 수 없음(README 원칙 재확인).
- 라벨은 n=1(소유자) 신규 수집. 척도(절대 평정 vs 쌍대비교)와 표본 크기는 착수 시 확정하되,
  **쌍대비교가 절대 평정보다 평정자 내 일관성이 높다는 점**을 고려한다.
- **과적합 재발 방지 조항**(이전 실패: rms_p90의 곡 1개 과적합):
  - GT 검증·학습 전에 **train/holdout 분리를 먼저** 하고 holdout은 최종 1회만 사용.
  - 통계 결합 대체안으로 회귀 학습 시 LOOCV + 정칙화 필수, 피처 수 상한(라벨 수의 1/10 이하).
  - 판정 기준(어떤 수치가 나오면 채택/기각인지)을 실행 전에 사전 등록.
- 1차 후보가 사전학습 연속 회귀 모델이므로 GT의 기본 역할은 **캘리브레이션 검증**(모델 출력과
  GT 간 단조성·순위 상관 확인)이다. 회귀 "학습"은 통계 결합 대체안으로 갈 때만 필요 — GT
  표본 부담이 그만큼 줄어든다.
- GT는 **동적 피처의 대표 요약통계 선택**(공통 규약 참조)에도 사용한다 — 중앙값/p90 등 후보
  중 지각 평가와 순위 상관이 가장 높은 것을 채택하며, 후보 목록과 판정 기준은 사전 등록.

## 분포 퇴화 탈출 조건

- 이 카탈로그(661곡)는 거의 전부 스튜디오 녹음 밴드 사운드 + 보컬곡이므로
  **acousticness·instrumentalness·liveness·speechiness는 분포가 좁은 저값 대역에 몰릴
  가능성이 큼**.
- 파일럿 단계에 4개 피처의 **분포 분산·변별력 점검을 필수 포함**하고, 변별력이 없다고
  판정되면 해당 피처는 우선순위를 강등한다(전수 산출은 하되 선곡 엔진 투입 보류). 핵심
  타깃은 energy·valence다.
- 강등 판정 기준(예: IQR 임계, 상위/하위 그룹 청취 대조 불일치율)은 파일럿 사전 등록에 포함.

## 전제 조건 (README.md에서 승계)

- **완전히 결정론적·비-ML로 가능**(proxy 불필요): tempo, key, mode, loudness.
- **개념이 거의 일치하는 오픈 자원 존재**(경한 proxy): energy·valence(arousal-valence 연속
  회귀), acousticness, instrumentalness.
- **원 개념과 거리가 있는 대체가 불가피한 완전 proxy**: liveness, danceability(ML 옵션 한정),
  speechiness(ML 교차검증 한정) — 가장 신중해야 할 지점.
- 모든 통계 결합 피쳐는 **자체 ground truth를 먼저 확보하고 그걸로 검증/학습**한다 — 임의
  균등 z-합 금지.
- 전부 **전곡 오디오** 기준이며 45초 발췌는 쓰지 않는다.
- Essentia/madmom/PANNs/inaSpeechSegmenter/pyannote는 2026-07 시점 오픈소스 사전학습
  자원이나, 착수 시점에 저장소·체크포인트 생존 여부는 재확인 필요. 실행은 전부 WSL2 환경.

## 다음 단계

1. WSL2 환경 구축 및 도구 설치 검증(특히 essentia-tensorflow의 emoMusic/DEAM 회귀 모델,
   madmom GitHub master, PANNs) — 버전·체크포인트 잠금.
2. ground truth 라벨 수집 설계 확정(척도, 표본 크기, train/holdout 분리) 및 판정 기준 사전 등록.
3. 피쳐별 파일럿(소표본): 집계 방식 후보 비교, speechiness↔tempo 상관 점검, tempo 옥타브
   정책 확정, liveness 오탐 청취 대조, 분포 퇴화 4종 변별력 점검.
4. 파일럿 통과 피처부터 정식 661곡 확장 — 확장 순서·판정 기준은 별도 사전 등록.
