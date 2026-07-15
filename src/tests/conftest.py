"""테스트 부트스트랩 — `src/backend`를 import 경로에 올려 `app.*`를 top-level로 임포트한다.

서버 구동은 `uvicorn app.main:app --app-dir src/backend`와 동일한 패키지 루트를 쓴다.
"""

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# `main`엔 data/가 없다 — backend는 기본적으로 `data` 브랜치를 원격 fetch한다
# (app.repo.remote_source). 테스트는 네트워크/원격 브랜치 존재 여부에 기대면 안 되므로,
# `app.main` import(모듈 레벨에서 create_app() 실행) 전에 SONGS_CSV를 고정 fixture로 override한다.
os.environ.setdefault("SONGS_CSV", str(Path(__file__).parent / "fixtures" / "songs_master.csv"))
