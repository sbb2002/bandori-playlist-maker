"""테스트 부트스트랩 — `src/backend`를 import 경로에 올려 `app.*`를 top-level로 임포트한다.

서버 구동은 `uvicorn app.main:app --app-dir src/backend`와 동일한 패키지 루트를 쓴다.
"""

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
