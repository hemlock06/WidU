"""L5 에스컬레이션 값 ↔ config 화이트리스트 일관성 (HANDOFF_ISSUES P2-6).

`FusionEngine._escalate` 가 실제로 반환할 수 있는 모든 escalation 문자열이
`config.L5.ESCALATION` 목록에 들어 있어야 한다. 과거 'self_check' 가 누락돼
소비측이 리스트로 검증하면 빠지는 문제가 있었다. 이 테스트가 재발을 막는다.

새 escalation 값을 추가하면서 ESCALATION 목록 갱신을 잊으면 여기서 실패한다.
"""
from __future__ import annotations

import ast
from pathlib import Path

from widu.config import L5

ROOT = Path(__file__).resolve().parents[1]
FUSION_SRC = ROOT / "widu" / "l5_fusion.py"


def _escalation_return_literals() -> set:
    """l5_fusion.py 의 _escalate 함수가 return 하는 문자열 리터럴을 정적 추출."""
    tree = ast.parse(FUSION_SRC.read_text(encoding="utf-8"))
    values: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_escalate":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant) \
                        and isinstance(sub.value.value, str):
                    values.add(sub.value.value)
    return values


def test_self_check_in_escalation_list():
    # P2-6 직접 가드: self_check 가 누락돼 있었음.
    assert "self_check" in L5.ESCALATION


def test_all_escalate_returns_are_whitelisted():
    returned = _escalation_return_literals()
    # 정적 추출이 비어 있으면(파싱 실패) 테스트 의미가 사라지므로 최소 1개 보장.
    assert returned, "could not statically extract escalation return values"
    missing = returned - set(L5.ESCALATION)
    assert not missing, f"_escalate returns values absent from L5.ESCALATION: {missing}"
