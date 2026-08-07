"""SentenceTransformer 기반 TextEmbedder 어댑터 — intfloat/multilingual-e5-small.

`data/lyric_impressions.json`의 곡 임베딩(오프라인 산출, 같은 모델·같은 "query: " 프리픽스)과
코사인 유사도를 비교하려면 이 어댑터도 반드시 같은 모델·같은 프리픽스를 써야 한다(다른 임베딩
공간끼리는 비교 불가). 모델은 프로세스당 1회만 로드하는 지연 싱글턴(콜드스타트 비용 최소화 —
`/api/setlist` 요청 중 impression이 있을 때만 실제로 로드된다).
"""

from __future__ import annotations

import threading

MODEL_NAME = "intfloat/multilingual-e5-small"
_PREFIX = "query: "  # e5 계열 권장 프리픽스(대칭 유사도 비교 시 양쪽 다 동일하게 적용).

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:  # 이중 체크(동시 요청 중복 로드 방지)
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(MODEL_NAME)
    return _model


class SentenceTransformerEmbedder:
    """`ports.embedding_port.TextEmbedder` 구현체."""

    def embed(self, text: str) -> list[float]:
        model = _get_model()
        vec = model.encode(_PREFIX + text, normalize_embeddings=True)
        return [float(x) for x in vec]
