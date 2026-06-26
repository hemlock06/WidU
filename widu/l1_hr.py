"""L1 — 개인화 심박 이상.

현 배포본(SCRUM-287 MA+고정임계)의 직접 후계.
핵심 개선 3가지:
  1) 맥락 조건부 기준선: (사용자 × 활동맥락)별 EWMA 평균/표준편차.
     → 같은 130bpm도 운동이면 정상, 안정이면 이상.
  2) 콜드스타트 prior: 표본 부족 시 연령대 모집단 분포로 시작 → 점진 개인화.
  3) 지속성 + 아티팩트 게이트: 단발/움직임 스파이크 억제.
견고성을 위해 이상으로 의심되는 표본은 기준선 갱신에서 제외(오염 방지).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from .types import HRSample, ActivityContext, AlertLevel, Detection
from .config import L1


class _CtxStat:
    """한 맥락의 온라인 평균/분산(EWMA)."""
    __slots__ = ("n", "mean", "var")

    def __init__(self, mean: float, var: float):
        self.n = 0
        self.mean = mean
        self.var = var

    def update(self, x: float, alpha: float):
        self.n += 1
        d = x - self.mean
        self.mean += alpha * d
        self.var = (1 - alpha) * (self.var + alpha * d * d)

    @property
    def std(self) -> float:
        return max(2.0, math.sqrt(max(self.var, 1e-6)))


class PersonalHRModel:
    """사용자 1인의 맥락별 심박 기준선 + 이상 판정."""

    def __init__(self, sustain_sec: Optional[float] = None,
                 rest_only: Optional[bool] = None):
        self._stat: Dict[str, _CtxStat] = {}
        self._sustain_start: Optional[float] = None
        self._sustain_level: AlertLevel = AlertLevel.NORMAL
        # 검증된 오탐 억제(애플=10분+비활동, ICU=지연, Stanford=안정심박만)
        self.sustain_sec = L1.SUSTAIN_SEC if sustain_sec is None else sustain_sec
        self.rest_only = L1.REST_ONLY if rest_only is None else rest_only

    def _stat_for(self, ctx: ActivityContext) -> _CtxStat:
        key = ctx.value
        if key not in self._stat:
            mean, std = L1.PRIOR.get(key, L1.PRIOR["UNKNOWN"])
            self._stat[key] = _CtxStat(mean, std * std)
        return self._stat[key]

    def baseline(self, ctx: ActivityContext) -> Tuple[float, float, int]:
        s = self._stat_for(ctx)
        return s.mean, s.std, s.n

    def update(self, hr: HRSample, ctx: ActivityContext,
               artifact_risk: bool = False) -> Optional[Detection]:
        # 안정시에만 탐지(Stanford/애플 '비활동 시'). 활동 중 심박은 아예 안 봄
        # → 활동추정 오류로 인한 오탐을 통째로 제거.
        if self.rest_only and ctx not in (ActivityContext.REST, ActivityContext.SLEEP):
            self._sustain_start = None
            self._sustain_level = AlertLevel.NORMAL
            return None
        s = self._stat_for(ctx)
        z = (hr.bpm - s.mean) / s.std
        az = abs(z)

        # 기준선 갱신: 정상 범위 표본만(이상 의심 표본은 제외 → 오염 방지)
        if az < L1.Z_CAUTION:
            s.update(hr.bpm, L1.EWMA_ALPHA)

        # 콜드스타트: 표본 부족 시 보수적으로(주의까지만)
        warming = s.n < L1.MIN_SAMPLES

        # 움직임 동반 고심박 스파이크는 아티팩트 가능 → 감점
        if artifact_risk and z > 0:
            az *= 0.5

        # 레벨 결정
        level = AlertLevel.NORMAL
        if az >= L1.Z_EMERGENCY and not warming:
            level = AlertLevel.EMERGENCY
        elif az >= L1.Z_CAUTION:
            level = AlertLevel.CAUTION

        # 지속성
        if level == AlertLevel.NORMAL:
            self._sustain_start = None
            self._sustain_level = AlertLevel.NORMAL
            return None
        if self._sustain_start is None or level.rank > self._sustain_level.rank:
            self._sustain_start = hr.ts
            self._sustain_level = level
        held = hr.ts - self._sustain_start
        if held < self.sustain_sec:
            return None

        direction = "high" if z > 0 else "low"
        return Detection(
            "L1", level, f"hr_{direction}", min(1.0, az / L1.Z_EMERGENCY), hr.ts,
            {"bpm": round(hr.bpm, 1), "z": round(z, 2), "context": ctx.value,
             "baseline_mean": round(s.mean, 1), "baseline_std": round(s.std, 1),
             "warming": warming, "sustained_s": round(held, 1)},
        )
