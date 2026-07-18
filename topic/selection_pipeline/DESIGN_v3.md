# selection_pipeline v3 — Method 1(프로덕션 그대로) vs Method 2(+ Stage C) 실측 비교

> **v1·v2와의 관계**: v1(`DESIGN.md`)·v2(`DESIGN_v2.md`)는 프로덕션 로직을 **단순 재현**(강도창
> 로직만 옮겨적음, 밝기 tie-break·Stage B 시퀀싱 생략)해서 비교했다는 게 2026-07-18 사용자
> 리뷰에서 드러났다 — 즉 그 두 라운드는 애초에 "실제 프로덕션 대비 개선 여부"를 검증하지 못했다.
> 이 문서는 **실제 프로덕션 코드를 그대로 재사용**해 처음부터 다시 설계한 독립 실험이다. v1·v2의
> 결론(§0 구조 기각, v2 판정 보류)은 그 자체로는 무효화되지 않지만(그 좁은 질문엔 유효한 답이었음),
> "가사 후보추림이 실제 프로덕션에 도움되는가"라는 원래 질문에는 이 v3가 처음으로 제대로 답한다.

## 0. 연구 질문·판정 기준

**RQ**: 실제 프로덕션 파이프라인(`build_setlist`)의 Stage A 직전에 **Stage C(가사 후보추림)**를
끼워 넣으면, 현재 배포판 대비 사용자 만족도가 개선되는가?

**Method 1(현재 배포판 그대로)**: 밴드 선택(풀 필터) → pool 검증 → 밝기 점수 사전계산 →
파라미터 제어(사용자 지정 > LLM 아크 > 기본 보간, 3분기) → **Stage A**(강도 선곡, 밝기
tie-break) → **Stage B**(시퀀싱) → 플레이리스트.

**Method 2(개정판)**: 동일한 파이프라인에 **Stage C를 Stage A 직전에 삽입** — 밴드 필터 적용 후
pool을 가사 코사인 유사도 상위 N(v1 arm2와 동일 방식: LLM 쿼리확장 → `BAAI/bge-m3` 임베딩 →
`N=max(15, ceil(0.20·|pool|))`)으로 좁힌 뒤, 그 축소된 pool 위에서 Stage A·B를 그대로 수행.

**판정**: 쿼리 단위 대응비교(Method2 3곡 평균 − Method1 3곡 평균, n=24쌍) Wilcoxon signed-rank,
양측 α=0.05. 이번 라운드는 **효과크기 사전 정보가 전혀 없는 첫 파일럿**이므로 특정 검정력을
목표로 n을 정하지 않았다(v1→v2에서 "이전 효과크기 가정으로 표본 크기를 정했다가 실제 효과가
더 작아서 도로 부족해진" 실수를 반복하지 않기 위함) — 결과를 보고 유의미한 방향성이 있으면 그때
정식 검정력 계산으로 2차 라운드를 설계한다.

## 1. 실제 프로덕션 코드 재사용 — 스냅샷 정책

`research` 브랜치는 `src/backend/`를 아예 추적하지 않는다(main과 분리 관리). 브랜치를 건드리지
않기 위해, **`origin/main`(pin: 커밋 `5d55187`, 2026-07-18 fetch 시점)의 아래 파일을 읽기 전용
스냅샷으로 `topic/selection_pipeline/prod_snapshot/`에 복사**해 그대로 import한다 — 로직을
옮겨 적지 않고 파일 자체를 가져온다(경로 배선만 vendoring에 맞게 조정 — `sys.path` 삽입 지점
2곳, `harmonic.py`·`song_repo.py`, 로직은 무변경):

| 원본 경로 | 역할 |
|---|---|
| `domain/models.py` | `Song`, `MoodParameters`, `StageSpec`, `Setlist` 등 |
| `domain/selection.py` | `build_setlist()` — Method 1은 이 함수를 **그대로 호출** |
| `domain/energy.py`, `domain/harmonic.py` | selection.py 의존성 |
| `repo/song_repo.py` | `data/songs_master.csv` 로더 + 검증된 강도(intensity) 산식 |
| `api/band_aliases.py` | `detect_bands()` — 결정론적 밴드 별명 매칭(LLM 아님) |
| `adapters/prompt.py` | `SYSTEM_PROMPT`·`RESPONSE_JSON_SCHEMA`·`build_messages`·`parse_mood` — 실제 배포 LLM 프롬프트 |
| `scripts/data/video_id.py` | song_repo 의존성(video_id 추출) |

Method 2는 `selection.py`를 복사해 Stage A 직전에 Stage C 삽입 블록만 추가한 새 파일
(`prod_snapshot/selection_stage_c.py`)로 만든다 — 나머지 로직(Stage A·B, 밝기 계산, 파라미터
분기)은 원본과 **1바이트도 다르지 않게** 유지한다(diff로 검증).

## 2. 데이터 소스 (연구용 CSV가 아니라 실제 배포 데이터)

- **곡 데이터**: `data/songs_master.csv`(661곡, `song_repo.load_songs()` 그대로 사용) — v1·v2가
  썼던 `topic/vector-embedding`의 `song_acoustics.csv` intensity가 아니라, **energy_full +
  acousticness_proxy + 시간분절 강도(i_min/i_mean/i_end)의 soft-OR 결합**(실제 검증된 값)을 쓴다.
- **가사 요약(Stage C용 `desc`)**: `topic/vector-embedding/src/method-1/out/song_profiles.csv`의
  `desc` 컬럼을 재사용한다. `songs_master.csv`(idx/band/song/url)와 벡터임베딩 카탈로그(tag)는
  **`url` 컬럼으로 661/661 완전 조인 확인됨**(`tag == f"{band}__{idx:03d}"` 패턴) — 새로 만들
  필요 없음.

## 3. MoodParameters 추출 — 실제 프로덕션 LLM 프롬프트 재사용

`prod_snapshot/adapters/prompt.py`의 `SYSTEM_PROMPT`·`build_messages`·`parse_mood`를 그대로
호출해 `brightness, start_energy, end_energy, stage_count, stage_energies, target_minutes, tags,
song_type, same_as_previous`를 추출한다(v1·v2처럼 intensity_target만 뽑는 축소판이 아님).

- **모델**: `llama-3.1-8b-instant` — `GroqMoodInterpreter`의 하드코딩 기본값(`.env`의
  `GROQ_MODEL=openai/gpt-oss-20b`는 배포 override라 DESIGN.md가 연구용으로 금지한 값, 사용 안 함).
  `llama-4-scout`(v1·v2가 원래 쓰려던 모델)는 Groq에서 서비스 자체가 내려가 사용 불가 확인됨.
- `temperature=0.2`, `response_format` 미전송(`response_format_mode="none"`, 프로덕션 기본과 동일).
- **밴드 필터**: `detect_bands(prompt)` 그대로 호출(별도 LLM 호출 없음, 결정론적).
- `previous_prompt`는 이 실험에서 항상 없음(1회성 요청만 다룸) → `same_as_previous`는 항상 False로
  귀결, `honor` 로직 자체가 이 실험 범위 밖(프로덕션의 세부설정 우선순위 기능은 다루지 않음).

## 4. 단일 스테이지 n=3곡 고정 — 통제된 비교를 위한 실험적 단순화

프로덕션은 자유 실행 시 `stage_count`(2~5)·`target_minutes`에 따라 곡 수가 가변적이다. 이번
실험은 "쿼리당 고정 n곡"으로 통제해야 Method1/2를 곡 수 차이 없이 공정 비교할 수 있으므로,
`stage_specs=[StageSpec(energy_target=params.start_energy, song_count=3)]`로 **강제로 단일
스테이지 3곡**만 생성한다.

- `energy_target`은 LLM이 뽑은 `params.start_energy`를 그대로 쓴다(단일 스테이지이므로 시작=끝
  구분이 없음 — 진행형 아크를 요청한 쿼리라도 이 실험에서는 대표값 하나로 축소됨. 이건 "고정 n곡"
  통제를 위해 의도적으로 포기하는 정보다 — §7 한계에 명시).
- Stage A·B는 프로덕션 코드 그대로 실행되므로, 밝기 tie-break·경계 연속성·하모닉 페널티가 전부
  실제로 작동한다(v1·v2가 생략했던 부분).
- **rng 시드**: 프로덕션은 매 요청 `rng=None`(비결정적)이지만, 이 실험은 통제 비교가 목적이므로
  **쿼리마다 고정 시드**(`random.Random(20260721_00 + query_index)`)를 만들어 **Method1·Method2
  양쪽에 동일하게 사용**한다 — 그래야 두 결과의 차이가 순수하게 "Stage C 유무" 때문이지 rng
  노이즈 때문이 아니라고 말할 수 있다.

## 5. 쿼리 세트 (신규 24개) — v2의 실수 반영

v2에서 "표현만 다르고 알고리즘이 보는 신호(intensity_target 스칼라 하나)로는 사실상 동의어인
쿼리를 카테고리당 21개씩 채워 곡 다양성이 붕괴"했던 실수(`report/02-*.md` §3)를 반복하지 않는다.
이번 v3의 `MoodParameters`는 스칼라 하나가 아니라 `brightness·start_energy·stage_energies` 등
다차원이라 붕괴 위험은 줄었지만, 그래도 쿼리 24개를 **서로 뚜렷이 다른 상황·표현**으로 설계한다.

| 카테고리 | 개수 | 설계 원칙 |
|---|---|---|
| 밴드지정 | 6 | 서로 다른 밴드 6개(중복 밴드 없음), 밝기/강도 표현도 각기 다르게 |
| 밴드미지정+절대강도/밝기 | 6 | 강도·밝기 극단을 고르게 분산(조용~시끄러움, 어두움~밝음), 표현도 다양화 |
| 상황/기능성 | 6 | 서로 다른 활동(운동/공부/드라이브/새벽/파티/휴식 등, v2와 겹치지 않는 문구) |
| 진행형 아크 요청 | 6 | "점점 고조되는", "준비-본운동-정리" 등 `stage_energies` 유도 쿼리(§4에서
어차피 start_energy로 축소되지만, 그 축소가 얼마나 정보를 버리는지 관찰할 겸 포함) |

### 5.1 쿼리 목록 (확정)

| id | 카테고리 | 쿼리 |
|---|---|---|
| R01 | 밴드지정 | poppin'party 노래로 신나게 하루 시작하고 싶어. |
| R02 | 밴드지정 | roselia 노래 중에 무겁고 진지한 분위기로 틀어줘. |
| R03 | 밴드지정 | raise a suilen 노래로 미친듯이 달리고 싶어. |
| R04 | 밴드지정 | mygo 노래로 조용히 감성에 잠기고 싶어. |
| R05 | 밴드지정 | ave mujica 노래로 스산하고 어두운 분위기 잡고 싶어. |
| R06 | 밴드지정 | hello happy world 노래로 밝고 유쾌하게 놀고 싶어. |
| R07 | 밴드미지정 강도/밝기 | 완전 조용하고 힘 빠진 노래로 채워줘. |
| R08 | 밴드미지정 강도/밝기 | 미친듯이 텐션 폭발하는 노래로 채워줘. |
| R09 | 밴드미지정 강도/밝기 | 햇살 가득한 것처럼 밝은 노래 듣고 싶어. |
| R10 | 밴드미지정 강도/밝기 | 칠흑같이 어둡고 무거운 노래 듣고 싶어. |
| R11 | 밴드미지정 강도/밝기 | 중간 정도 텐션에 살짝 우울한 느낌으로. |
| R12 | 밴드미지정 강도/밝기 | 살짝 들뜨는데 시끄럽진 않은 노래로. |
| R13 | 상황/기능성 | 헬스장에서 웨이트 할 때 들을 노래. |
| R14 | 상황/기능성 | 독서할 때 배경으로 틀어놓을 노래. |
| R15 | 상황/기능성 | 장거리 운전할 때 졸음 안 오게 들을 노래. |
| R16 | 상황/기능성 | 빨래 개면서 듣기 좋은 노래. |
| R17 | 상황/기능성 | 친구 생일파티에서 틀 노래. |
| R18 | 상황/기능성 | 잠들기 전 조명 끄고 듣는 노래. |
| R19 | 진행형 아크 | 달리기 준비운동부터 본운동, 마무리까지 이어지는 러닝 플레이리스트. |
| R20 | 진행형 아크 | 천천히 달아오르는 파티 분위기로 만들어줘. |
| R21 | 진행형 아크 | 가라앉은 기분에서 서서히 힘을 되찾는 느낌으로. |
| R22 | 진행형 아크 | 공부 시작할 때 차분하다가 집중력 오르면서 점점 몰입되는 느낌으로. |
| R23 | 진행형 아크 | 새벽 드라이브, 조용히 출발해서 해뜰 때쯤 신나지는 느낌으로. |
| R24 | 진행형 아크 | 운동 마무리하고 차분히 식히는 쿨다운 느낌으로. |

밴드지정 6개는 서로 다른 밴드(poppin_party·roselia·raise_a_suilen·mygo·ave_mujica·
hello_happy_world)로 겹치지 않게 배정 — v2처럼 같은 신호로 수렴할 위험 자체가 구조적으로 낮다
(밴드가 다르면 eligible_pool 자체가 다름).

## 6. 블라인드 평가

- Method1·Method2 각 3곡 → 쿼리당 최대 6곡(중복 시 더 적음), 24쿼리 전체 최대 144개 항목.
- v2와 동일하게 1~5 Likert, 곡 단위 채점(쿼리별 3곡 평균으로 대응비교).
- 카테고리·메서드 정체 노출 금지(v2의 블라인딩 사고 재발 방지 — 메뉴는 평평한 목록만).
- 모바일 아티팩트 재사용(유튜브 iframe, localStorage 자동저장, `window.claude.downloads` 내보내기).

## 7. 알려진 한계 (착수 시점)

- 단일 스테이지 3곡 고정은 실제 사용자 경험(가변 길이 세트리스트)을 단순화한 것 — 진행형 아크
  요청의 "고조되는 흐름" 체감은 이 실험에서 측정되지 않는다.
- rng 시드 고정은 통제를 위한 것이라, 프로덕션의 실제 무작위성(같은 요청도 매번 다른 결과)은
  이 실험 결과에 반영되지 않는다.
- Q=24는 특정 검정력을 겨냥한 값이 아니라 v1·v2 경험상 다루기 쉬웠던 규모의 파일럿이다 — 결과가
  애매하면 §0처럼 사후 검정력 계산으로 2차 라운드를 판단한다.
- Stage C의 후보추림 방식(LLM 확장+bge-m3, 상위 20%)은 v1 arm2를 그대로 재사용 — 이 방식 자체의
  대안(다른 N, 다른 임베딩 모델)은 이번 라운드 범위 밖.

## 8. 실행 기록 (2026-07-18)

- 코드 재사용은 계획대로 진행: `build_setlist()` 패스스루(lyric_scores=None) 결과가
  `build_setlist_with_stage_c()`와 동일 시드에서 **완전히 동일**함을 사전 확인(포크의 Stage A·B
  로직이 원본과 정확히 일치한다는 증거).
- `llama-3.1-8b-instant`가 살아있어 별도 모델 대체 없이 계획대로 사용.
- **밴드 별명 오탐 1건 발견(연구 범위 밖, 프로덕션 자체 특성)**: R19("...러닝 **플레이리스트**")가
  `detect_bands()`에서 `raise_a_suilen`으로 오판정됨 — "플레이리스트"의 "레이" 부분 문자열이
  `raise_a_suilen`의 짧은 별명("레이")과 우연히 매칭됐다. `band_aliases.py` 자체 docstring이
  이미 "짧은 별명은 오탐 여지가 있으나 의도적 언급으로 간주"라고 밝힌 기존 트레이드오프이며, 이
  실험이 만든 버그가 아니라 **재사용된 프로덕션 코드의 실제 동작**이므로 수정하지 않고 그대로
  둠 — Method1·Method2 둘 다 동일하게 영향받아 비교 공정성은 유지된다.
- **곡 다양성 붕괴 재발 없음**(v2의 핵심 실패 재현 안 됨): method1 72항목 중 고유곡 50개,
  method2 72항목 중 고유곡 52개 — 최다 반복도 3회 이하 수준. 실제 `MoodParameters`가 스칼라
  하나가 아니라 `brightness·start_energy` 등 다차원이고, Stage B 시퀀싱(하모닉·경계 연속성)이
  곡 조합에 변주를 더한 게 원인으로 보인다.
- 블라인드 시트: 원시 144쌍 중 실제 고유 **127쌍**(중복률 12% — v2의 21%보다 낮음).
- 채점 아티팩트: https://claude.ai/code/artifact/bc547556-1776-4067-a2ad-37e35f5c14a9
  (유튜브 임베드, 카테고리 비노출 평평한 메뉴, `window.claude.downloads`로 JSON 내보내기).
- **결과·카테고리별 세부·특이 케이스·플롯/다이어그램**: `report/03-selection_pipeline_v3_method_comparison.md`
  참조(전체 비유의, 카테고리 패턴은 v1·v2·v3 세 라운드 연속 재현되나 개별 유의성은 없음(n=6/카테고리),
  R01/R19 밴드 별명 매칭 사각지대, R24 단일스테이지 축소의 실측 대가 등).
