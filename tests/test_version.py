"""버전 단일 출처 일관성 (HANDOFF_ISSUES P2-1).

과거 `widu/__init__.py`(__version__ = "0.1.0") 와 `pyproject.toml`(version = "0.20.0")
가 달랐다. 이제 __init__ 은 패키지 메타데이터(설치본) 또는 동일 폴백을 쓰므로
pyproject 의 버전과 일치해야 한다.

tomllib 없이(파이썬 3.9 호환) 정규식으로 pyproject 버전을 읽는다.
"""
from __future__ import annotations

import re
from pathlib import Path

import widu

ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^\s*version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "version not found in pyproject.toml"
    return m.group(1)


def test_version_is_nonempty_string():
    assert isinstance(widu.__version__, str)
    assert widu.__version__


def test_version_matches_pyproject():
    assert widu.__version__ == _pyproject_version()
