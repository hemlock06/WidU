"""L1(개인화 심박) 단위 테스트 — 검증된 게이팅·지속성만 보수적으로 박제.

핵심 계약(widu/l1_hr.py):
  - rest_only: 활동(ACTIVE/LOW) 맥락에서는 아예 탐지하지 않는다(오탐 제거).
  - 지속성: 이상 z 가 SUSTAIN_SEC(180s) 이상 유지돼야 Detection.
  - 정상 z 표본만 baseline EWMA 갱신(이상치는 baseline 오염 방지로 제외).
"""
from __future__ import annotations

import pytest

from widu.l1_hr import PersonalHRModel
from widu.types import HRSample, ActivityContext, AlertLevel
from widu.config import L1


def _feed(model, bpm, ctx, dur_s, step_s=1.0, t0=0.0):
    """bpm 을 dur_s 동안 흘리며 마지막 Detection 반환."""
    det = None
    t = t0
    end = t0 + dur_s
    while t <= end:
        d = model.update(HRSample(t, bpm), ctx)
        if d is not None:
            det = d
        t += step_s
    return det, t


def test_active_context_never_detects():
    # rest_only=True 이므로 ACTIVE 맥락의 고심박은 무시(정상 빈맥 오탐 차단)
    m = PersonalHRModel()
    det, _ = _feed(m, 160.0, ActivityContext.ACTIVE, dur_s=600.0)
    assert det is None


def test_normal_resting_hr_no_alert():
    m = PersonalHRModel()
    det, _ = _feed(m, 72.0, ActivityContext.REST, dur_s=600.0)
    assert det is None


def test_sustained_high_resting_hr_fires_hr_high():
    m = PersonalHRModel()
    # 1) baseline 워밍업(정상 72bpm) — 콜드스타트 탈출(MIN_SAMPLES)
    _, t = _feed(m, 72.0, ActivityContext.REST, dur_s=120.0)
    # 2) 명확히 상승한 심박을 지속성(>180s) 이상 유지 → hr_high
    det, _ = _feed(m, 120.0, ActivityContext.REST, dur_s=240.0, t0=t + 1.0)
    assert det is not None
    assert det.scenario == "hr_high"
    assert det.level in (AlertLevel.CAUTION, AlertLevel.EMERGENCY)
    assert det.layer == "L1"


def test_short_spike_does_not_fire():
    m = PersonalHRModel()
    _, t = _feed(m, 72.0, ActivityContext.REST, dur_s=120.0)
    # 지속성(180s) 미만의 짧은 상승은 발화 금지
    det, _ = _feed(m, 120.0, ActivityContext.REST, dur_s=30.0, t0=t + 1.0)
    assert det is None


def test_config_constants():
    assert L1.SUSTAIN_SEC == 180
    assert L1.REST_ONLY is True
    assert L1.Z_CAUTION == 3.0
    assert L1.Z_EMERGENCY == 4.5


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
