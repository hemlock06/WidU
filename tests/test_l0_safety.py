"""L0(결정적 안전룰) 단위 테스트 — 검증된 동작만 보수적으로 박제.

L0Safety.update(HRSample, ActivityContext) 는 임계+지속성(SUSTAIN_SEC=30s)을
만족할 때만 Detection 을 낸다. 단발 샘플로는 발화하지 않아야 한다.
임계값은 widu/config.py:L0 에서 검증(서맥<40·빈맥>150·무박동<25·안정빈맥>130).
"""
from __future__ import annotations

import pytest

from widu.l0_safety import L0Safety
from widu.types import HRSample, ActivityContext, AlertLevel, Accuracy
from widu.config import L0


def _sustain(bpm: float, ctx: ActivityContext, dur_s: float = 70.0,
             step_s: float = 2.0):
    """주어진 bpm 을 dur_s 동안 ctx 에서 흘려보낸 뒤 마지막 Detection 반환."""
    l0 = L0Safety()
    det = None
    t = 0.0
    while t <= dur_s:
        d = l0.update(HRSample(t, bpm, Accuracy.HIGH), ctx)
        if d is not None:
            det = d
        t += step_s
    return det


def test_normal_hr_no_alert():
    assert _sustain(70.0, ActivityContext.REST) is None


def test_severe_bradycardia_fires():
    det = _sustain(35.0, ActivityContext.REST)
    assert det is not None
    assert det.scenario == "bradycardia"
    assert det.level == AlertLevel.EMERGENCY
    assert det.layer == "L0"


def test_severe_tachycardia_fires():
    det = _sustain(160.0, ActivityContext.REST)
    assert det is not None
    assert det.scenario == "tachycardia"
    assert det.level == AlertLevel.EMERGENCY


def test_flatline_fires():
    # bpm < HR_FLATLINE(25) — 무박동/실신·정지 의심 (flatline 이 brady 보다 우선)
    det = _sustain(22.0, ActivityContext.REST)
    assert det is not None
    assert det.scenario == "flatline_arrest"
    assert det.level == AlertLevel.EMERGENCY


def test_resting_tachycardia_only_when_resting():
    # 안정맥락 + HR_TACHY_REST(130) 초과(하드 150 미만) → resting_tachycardia
    det_rest = _sustain(140.0, ActivityContext.REST)
    assert det_rest is not None
    assert det_rest.scenario == "resting_tachycardia"
    # 같은 140bpm 이라도 ACTIVE(운동) 맥락이면 안정빈맥 룰은 억제(오경보 방지)
    det_active = _sustain(140.0, ActivityContext.ACTIVE)
    assert det_active is None


def test_single_sample_does_not_fire():
    # 지속성(SUSTAIN_SEC) 미충족 — 단발 이상치는 발화 금지
    l0 = L0Safety()
    assert l0.update(HRSample(0.0, 35.0, Accuracy.HIGH), ActivityContext.REST) is None


def test_sustain_threshold_value():
    # 설정 상수 회귀 가드(임계가 바뀌면 운영 의미가 달라지므로 명시 고정)
    assert L0.HR_BRADY_HARD == 40
    assert L0.HR_TACHY_HARD == 150
    assert L0.HR_FLATLINE == 25
    assert L0.SUSTAIN_SEC == 30


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
