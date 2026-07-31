# method-3-mode 구현 스펙

> `../CONVENTIONS.md` 선행 필독. 개념 근거는 `./README.md`, `../DESIGN.md` §3.

## 실행 환경
- **네이티브** — 별도 오디오 처리 없음. `method-2-key/out/key_raw.csv`를 읽기만 한다.

## 산출물

별도 오디오 추출 스크립트 없음. 대신 `build_mode_report.py` 1개만 작성:

```python
"""method-2-key/out/key_raw.csv를 읽어 mode 신뢰도 리포트를 만든다.
오디오를 새로 열지 않는다 — key 산출의 부산물이라는 설계를 코드로도 강제."""

def main():
    # ../method-2-key/out/key_raw.csv 로드
    # mode = mode_ks 컬럼을 그대로 mode(장/단조)로 채택
    # 신뢰도 리포트: mode_only_mismatch 비율(essentia 교차검증 있는 행만 대상)을 out/mode_report.md에 기록
    # out/mode_raw.csv: idx, band, song, mode, mode_confidence_note 로 단순 재노출(엔진 투입 편의용 뷰)
    ...
```

`out/mode_raw.csv`:
```
idx, band, song, mode           # "major" / "minor", key_raw.csv의 mode_ks 그대로
```
`out/mode_report.md`: mode_only_mismatch 비율, 불일치 상위 사례(청취 스팟체크 후보) 요약.

## 구현 시 주의
- `method-2-key/out/key_raw.csv`가 아직 없으면 명확한 에러 메시지로 즉시 종료
  (`"먼저 method-2-key를 실행하세요: ../method-2-key/out/key_raw.csv 없음"`).
- 이 스크립트는 **오디오 파일을 전혀 열지 않는다** — CONVENTIONS의 오디오 경로 상수도 import
  하지 않는다(설계상 key의 순수 부산물임을 코드 구조로 보여줌).

## 검증 방법 (내가 수행)
- method-2-key 결과가 나온 뒤 즉시 네이티브로 실행·검증 가능(외부 의존성 없음).
