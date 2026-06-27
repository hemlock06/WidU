"""pytest 부트스트랩 — 레포 루트를 sys.path 에 올려 `widu`/`serving` import 보장.

(추가 파일. 기존 소스는 건드리지 않는다. scripts/*.py 와 동일한 ROOT 부트스트랩 관례.)
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
