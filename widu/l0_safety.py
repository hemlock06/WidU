"""L0 — 결정적 안전룰.

놓치면 안 되는 명백한 임상 이벤트를 임계+지속성으로 잡는다.
라벨 불필요·즉시·설명가능. 개인화(L1)와 독립적으로 항상 동작하는 바닥.
지속성(SUSTAIN_SEC) 요구로 단발 아티팩트를 거른다.
"""
from __future__ import annotations

from typing import Optional, Dict

from .types import HRSample, ActivityContext, AlertLevel, Detection
from .config import L0


class _Sustain:
    """조건이 연속으로 유지된 시간을 추적."""
    def __init__(self):
        self._start: Optional[float] = None

    def update(self, holds: bool, ts: float) -> float:
        if holds:
            if self._start is None:
                self._start = ts
            return ts - self._start
        self._start = None
        return 0.0


class L0Safety:
    def __init__(self):
        self._flat = _Sustain()
        self._brady = _Sustain()
        self._tachy = _Sustain()
        self._tachy_rest = _Sustain()

    def update(self, hr: HRSample, ctx: ActivityContext) -> Optional[Detection]:
        b = hr.bpm
        ts = hr.ts
        ev: Dict[str, float] = {"bpm": b}

        # 1) 무박동/실신·정지 의심
        if self._flat.update(b < L0.HR_FLATLINE, ts) >= L0.SUSTAIN_SEC:
            return Detection("L0", AlertLevel.EMERGENCY, "flatline_arrest", 1.0, ts,
                             {**ev, "rule": f"bpm<{L0.HR_FLATLINE} {L0.SUSTAIN_SEC}s"})

        # 2) 중증 서맥
        if self._brady.update(b < L0.HR_BRADY_HARD, ts) >= L0.SUSTAIN_SEC:
            return Detection("L0", AlertLevel.EMERGENCY, "bradycardia", 0.95, ts,
                             {**ev, "rule": f"bpm<{L0.HR_BRADY_HARD} {L0.SUSTAIN_SEC}s"})

        # 3) 중증 빈맥(맥락 무관)
        if self._tachy.update(b > L0.HR_TACHY_HARD, ts) >= L0.SUSTAIN_SEC:
            return Detection("L0", AlertLevel.EMERGENCY, "tachycardia", 0.95, ts,
                             {**ev, "rule": f"bpm>{L0.HR_TACHY_HARD} {L0.SUSTAIN_SEC}s"})

        # 4) 안정 상태에서의 빈맥(운동맥락이면 억제 → 오경보 방지)
        resting = ctx in (ActivityContext.REST, ActivityContext.SLEEP)
        if self._tachy_rest.update(resting and b > L0.HR_TACHY_REST, ts) >= L0.SUSTAIN_SEC:
            return Detection("L0", AlertLevel.EMERGENCY, "resting_tachycardia", 0.9, ts,
                             {**ev, "rule": f"rest & bpm>{L0.HR_TACHY_REST} {L0.SUSTAIN_SEC}s",
                              "context": ctx.value})

        return None
