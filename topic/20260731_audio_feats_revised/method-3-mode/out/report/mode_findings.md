# Mode (Major/Minor) Distribution — Method-3 분석

## 개요

본 분석은 **method-2-key에서 산출된 key_ks(Keygram + K-S 템플릿 매칭) 기반의 mode(장/단조) 값**을 사용하여, 최종 채택된 조성 정보의 밴드별 분포를 정리한 보고서다.

### 신뢰도 참고사항

method-2-key의 검증 결과에 따르면:
- **mode만 일치율: 73.9%** (K-S vs Essentia 교차검증)
- 정확한 조성(key)은 불일치율 39.4%로 높지만, 장/단조 구분만으로는 훨씬 안정적
- roselia·raise_a_suilen은 mode 자체가 불안정 (63.3%, 67.0% 일치율)
- morfonica의 A minor 쏠림은 cover 곡 선곡 경향 + 알고리즘 특성 혼합

## 전체 분포 (736곡)

| Mode | 곡수 | 비율 |
|---|---|---|
| **Major** | **419** | **56.9%** |
| **Minor** | **317** | **43.1%** |

전체적으로 major 쏠림이 명확한데, 이는 밴드별로 편차가 크다(아래 참고).

## 밴드별 분포 (10곡 이상, 계 728곡)

| 밴드 | 표본(n) | Major | Minor | Major % |
|---|---|---|---|---|
| **hello_happy_world** | 72 | 54 | 18 | **75.0%** |
| **afterglow** | 72 | 53 | 19 | **73.6%** |
| **pastel_palettes** | 74 | 54 | 20 | **73.0%** |
| **poppin_party** | 116 | 81 | 35 | **69.8%** |
| **mygo** | 60 | 38 | 22 | **63.3%** |
| **mugendai_mutype** | 77 | 37 | 40 | **48.1%** |
| **morfonica** | 58 | 22 | 36 | **37.9%** |
| **ave_mujica** | 29 | 10 | 19 | **34.5%** |
| **raise_a_suilen** | 79 | 29 | 50 | **36.7%** |
| **roselia** | 91 | 35 | 56 | **38.5%** |

분석 대상: 728곡 (10곡 미만 3개 밴드 제외)

## 특이 패턴

### 1. Major 쏠림 그룹 (73%+)
- **afterglow, hello_happy_world, pastel_palettes** — 세 밴드 모두 73% 이상 major
- 특징: 밝고 경쾌한 분위기의 곡 비율이 높음
- 이들 밴드는 mode 신뢰도 측면에서도 method-2-key 분석 시 상위권

### 2. Minor 쏠림 그룹 (63%+ minor)
- **roselia (61.5% minor), raise_a_suilen (63.3% minor), morfonica (62.1% minor), ave_mujica (65.5% minor)**
- 특징: 어두운 톤, 메탈·록 성향 또는 감성적 발라드 비율이 높음
- **⚠️ 주의**: method-2-key에서 이들 밴드의 mode 신뢰도가 하위권임을 명시했다
  - roselia: 67.0% 일치율 (K-S vs Essentia)
  - raise_a_suilen: 63.3% 일치율
  - morfonica: 77.6% 일치율 (상대적으로 개선, A minor 쏠림은 설명됨)

### 3. 균등 분포
- **mugendai_mutype (48.1% major, 51.9% minor)** — 가장 균형 잡힌 분포
- 밴드 특성상 다양한 곡 스타일을 포함하는 것으로 추정

### 4. Minor 쏠림의 근본 원인 (method-2-key 참고)
- roselia: 밴드 자체의 작곡/연주 성향 (락/메탈 밴드로서 E minor 등 darker key 선호)
- morfonica: 근친조(A minor ↔ D/E minor) 혼동 + 커버곡 선곡 경향
- 이들은 **K-S 템플릿 매칭의 한계**를 보여주는 사례이며, 정확한 조성 판정은 50곡 청취 스팟체크(REPORT.md 인계 대기)가 필요

## 데이터 출처 및 제약

- **산출물**: method-2-key의 `key_raw.csv` (K-S 알고리즘)에서 추출된 mode 컬럼
- **중복 분석 방지**: 본 보고서는 **mode의 밴드별 분포만 정리**하며, 알고리즘 신뢰도·근친조 혼동·cover곡 영향 등 상세 분석은 method-2-key `key_findings.md`에 기록됨 (중복하지 않음)
- **한계**: mode만 73.9% 안정적이나, 정확한 조성(key)은 여전히 신뢰도가 낮음

## 결론

1. 전체 major:minor = 419:317 (56.9% : 43.1%)
2. 밴드별로 편차가 매우 큼 (major % 범위: 34.5% ~ 75.0%)
3. roselia·raise_a_suilen·morfonica·ave_mujica는 minor 쏠림이 강하며, **mode 신뢰도가 상대적으로 낮음**
4. 이 데이터는 K-S 알고리즘 기반이므로, 정확한 조성 검증이 필요한 경우 청취 스팟체크가 권장됨
