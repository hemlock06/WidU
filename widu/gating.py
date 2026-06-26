"""게이팅 — 원신호를 신뢰 가능한 상태로 정제한다(L0 앞단).

오경보의 절반은 여기서 걸린다:
  1) 심박 품질 게이트: accuracy 가 신뢰 불가면 폐기, NO_CONTACT 지속이면 '미착용'.
  2) 활동 맥락 추정: 가속도에서 {수면/안정/저활동/운동} → HR 정상범위를 조건부로.
  3) 모션 아티팩트: 움직임 동반 HR 스파이크 감점(상위 계층에 컨텍스트 제공).
"""
from __future__ import annotations

import math
import time
from collections import deque
from datetime import datetime
from typing import Optional, Tuple

from .types import HRSample, IMUSample, Accuracy, ActivityContext
from .config import Activity


def quality_gate(hr: HRSample) -> Tuple[bool, bool]:
    """(use_sample, is_no_contact) 반환.

    use_sample=False 인 표본은 L1/L0 계산에서 제외한다.
    """
    if hr.accuracy == Accuracy.NO_CONTACT:
        return False, True
    if hr.accuracy in (Accuracy.UNRELIABLE,):
        return False, False
    # 생리적으로 불가능한 값 폐기
    if not (20.0 <= hr.bpm <= 240.0):
        return False, False
    return True, False


class ActivityEstimator:
    """최근 가속도 윈도우의 동적 성분(SMA)으로 활동 맥락을 추정."""

    def __init__(self, fs_hint: float = 25.0):
        self.win_n = max(8, int(Activity.WIN_SEC * fs_hint))
        self._buf: deque[float] = deque(maxlen=self.win_n)
        self._last_ctx = ActivityContext.UNKNOWN

    @staticmethod
    def _dynamic_g(s: IMUSample) -> float:
        smv = math.sqrt(s.ax * s.ax + s.ay * s.ay + s.az * s.az)
        return abs(smv - 1.0)  # 중력 제거한 동적 성분

    def update(self, s: IMUSample) -> ActivityContext:
        self._buf.append(self._dynamic_g(s))
        if len(self._buf) < max(4, self.win_n // 2):
            return self._last_ctx
        sma = sum(self._buf) / len(self._buf)
        hour = datetime.fromtimestamp(s.ts).hour
        if sma < Activity.SMA_REST:
            ctx = ActivityContext.SLEEP if (hour >= 23 or hour < 6) else ActivityContext.REST
        elif sma < Activity.SMA_LOW:
            ctx = ActivityContext.LOW
        else:
            ctx = ActivityContext.ACTIVE
        self._last_ctx = ctx
        return ctx

    @property
    def context(self) -> ActivityContext:
        return self._last_ctx

    @property
    def recent_sma(self) -> Optional[float]:
        if not self._buf:
            return None
        return sum(self._buf) / len(self._buf)

    def is_motion_artifact_risk(self) -> bool:
        """움직임이 큰 동안의 HR 스파이크는 아티팩트일 확률↑."""
        sma = self.recent_sma
        return sma is not None and sma >= Activity.SMA_ACTIVE
