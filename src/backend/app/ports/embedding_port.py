"""TextEmbedder 포트 — 짧은 텍스트 → 임베딩 벡터 인터페이스.

도메인·API는 이 인터페이스만 알며 sentence-transformers 등 구현 세부를 모른다.
`typing.Protocol`을 쓰므로 어댑터는 상속 없이 구조적 준수만으로 포트를 만족한다.
"""

from __future__ import annotations

from typing import Protocol


class TextEmbedder(Protocol):
    """텍스트 임베딩 포트. 구현은 `adapters/` 하위 단일 파일(모델별)."""

    def embed(self, text: str) -> list[float]:
        """텍스트 1건을 임베딩 벡터로 변환한다(L2-정규화됨, 코사인 유사도 = 내적).

        Args:
            text: 임베딩할 텍스트(예: 스테이지 가사 감상 1문장).

        Returns:
            정규화된 float 벡터. 모델 차원은 구현체가 결정(현재 384, e5-small).
        """
        ...
