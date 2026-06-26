"""L4 — 느린 추세(기록형 신호).

SpO2·체온·HRV·안정심박은 실시간 불가 → 응급이 아니라 '조기경보'로 위치.
일일 개인 베이스라인 + CUSUM 변화점 탐지.
대표 사례: 안정심박 상승 추세 → 감염(독감/폐렴/코로나) 조기경보(Stanford 선례).
이 계층은 Phase4 'AI 기저질환 조기진단'의 씨앗이다.
"""
from __future__ import annotations

from collections import deque
from typing import Dict, Optional

from .types import RecordSample, RecordKind, AlertLevel, Detection
from .config import L4


class _Baseline:
    """일일 값의 베이스라인 + 단방향 CUSUM."""
    def __init__(self, days: int, direction: int):
        self.vals: deque[float] = deque(maxlen=days)
        self.cusum = 0.0
        self.direction = direction  # +1 상승 감지, -1 하강 감지

    @property
    def mean(self) -> Optional[float]:
        return sum(self.vals) / len(self.vals) if self.vals else None

    def update(self, x: float, k: float) -> float:
        m = self.mean
        self.vals.append(x)
        if m is None:
            return 0.0
        dev = self.direction * (x - m) - k
        self.cusum = max(0.0, self.cusum + dev)
        return self.cusum


class TrendMonitor:
    """사용자 1인의 느린 추세 감시."""

    def __init__(self):
        self._b: Dict[str, _Baseline] = {
            "RESTING_HR": _Baseline(L4.BASELINE_DAYS, +1),
            "SPO2": _Baseline(L4.BASELINE_DAYS, -1),
            "TEMP": _Baseline(L4.BASELINE_DAYS, +1),
            "HRV": _Baseline(L4.BASELINE_DAYS, -1),
        }

    def update(self, rec: RecordSample) -> Optional[Detection]:
        key = rec.kind.value
        if key not in self._b:
            return None
        b = self._b[key]
        prev_mean = b.mean
        cusum = b.update(rec.value, L4.CUSUM_K)

        # 안정심박 상승 추세 → 감염 조기경보
        if rec.kind == RecordKind.RESTING_HR and prev_mean is not None:
            if (rec.value - prev_mean) >= L4.RESTING_HR_DELTA and cusum > L4.CUSUM_H:
                return Detection("L4", AlertLevel.INFO, "resting_hr_uptrend", 0.6, rec.ts,
                                 {"resting_hr": rec.value, "baseline": round(prev_mean, 1),
                                  "hint": "감염/컨디션 저하 조기 신호 가능"})

        # SpO2 추세 저하(기록형)
        if rec.kind == RecordKind.SPO2 and rec.value < L4.SPO2_TREND:
            return Detection("L4", AlertLevel.INFO, "spo2_low_trend", 0.55, rec.ts,
                             {"spo2": rec.value, "threshold": L4.SPO2_TREND,
                              "note": "기록형 신호 — 응급 트리거 아님"})

        # 체온 상승 추세
        if rec.kind == RecordKind.TEMP and prev_mean is not None:
            if (rec.value - prev_mean) >= 0.7 and cusum > L4.CUSUM_H:
                return Detection("L4", AlertLevel.INFO, "temp_uptrend", 0.55, rec.ts,
                                 {"temp": rec.value, "baseline": round(prev_mean, 1)})
        return None
