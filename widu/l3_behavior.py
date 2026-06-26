"""L3 — 행동·위치 개인화.

지오펜스(안전구역 이탈 150m, 배포됨) + 무활동(12h) + 체류 + 배회.
프라이버시: 지오펜싱은 원좌표가 아니라 '안전구역 대비 거리/이탈'만 남긴다.
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from .types import LocSample, ActivityContext, AlertLevel, Detection
from .config import L3


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


class BehaviorMonitor:
    """사용자 1인의 위치·활동 기반 행동 이상 감시."""

    def __init__(self):
        self.safe_zones: List[Tuple[float, float, float]] = []  # (lat,lon,radius_m)
        self._last_active_ts: Optional[float] = None
        self._last_seen_ts: Optional[float] = None
        self._last_loc: Optional[LocSample] = None
        self._outside_since: Optional[float] = None
        self._immobility_fired = False
        self._impact_ts: Optional[float] = None       # 최근 낙상급 충격 시각
        self._unrecovered_fired = False

    def set_safe_zones(self, zones: List[Tuple[float, float, float]]):
        self.safe_zones = zones

    def note_impact(self, ts: float, mag: float):
        """L2 가 낙상급 충격을 알리면 '미회복' 감시를 무장(FP 억제 위해 큰 충격만)."""
        if mag >= L3.POST_FALL_ARM_G:
            self._impact_ts = ts
            self._unrecovered_fired = False

    # --- 활동 무활동 감시 ------------------------------------------------- #
    def update_activity(self, ctx: ActivityContext, ts: float) -> Optional[Detection]:
        # 데이터 공백(워치 꺼짐/연결끊김)을 무활동으로 오인 금지 → 공백 시 시계 리셋
        if self._last_seen_ts is not None and (ts - self._last_seen_ts) > L3.IMMOBILE_GAP_RESET_SEC:
            self._last_active_ts = ts
            self._immobility_fired = False
            self._impact_ts = None
        self._last_seen_ts = ts

        moving = ctx in (ActivityContext.LOW, ActivityContext.ACTIVE)

        # 중간지평 '넘어진 뒤 미회복' — 충격 후 N분 무활동(고령 오분류 낙상 안전망)
        # 충격 직후 grace 동안의 안정화 모션은 '회복'으로 보지 않음(추정기 지연 흡수).
        if self._impact_ts is not None:
            dt = ts - self._impact_ts
            if moving and dt > L3.POST_FALL_GRACE_SEC:   # 안정화 후 움직임 = 회복
                self._impact_ts = None
            elif (not moving) and dt >= L3.POST_FALL_WATCH_SEC and not self._unrecovered_fired:
                self._unrecovered_fired = True
                self._impact_ts = None
                return Detection("L3", AlertLevel.EMERGENCY, "fall_unrecovered", 0.85, ts,
                                 {"since_impact_s": round(dt)})

        if moving:
            self._last_active_ts = ts
            self._immobility_fired = False
            return None
        if self._last_active_ts is None:
            self._last_active_ts = ts
            return None
        idle = ts - self._last_active_ts
        if idle >= L3.IMMOBILE_HARD_SEC and not self._immobility_fired:
            self._immobility_fired = True
            return Detection("L3", AlertLevel.EMERGENCY, "immobility_12h", 0.9, ts,
                             {"idle_hours": round(idle / 3600, 1)})
        return None

    # --- 위치(지오펜스·배회) --------------------------------------------- #
    def update_location(self, loc: LocSample) -> Optional[Detection]:
        self._last_loc = loc
        if not self.safe_zones:
            return None
        dmin = min(haversine_m(loc.lat, loc.lon, z[0], z[1]) - z[2]
                   for z in self.safe_zones)
        outside = dmin > 0  # 모든 안전구역 밖
        hour = _hour(loc.ts)
        night = hour >= L3.WANDER_NIGHT_START or hour < L3.WANDER_NIGHT_END

        if not outside:
            self._outside_since = None
            return None

        if self._outside_since is None:
            self._outside_since = loc.ts

        # 야간 이탈 = 배회 의심(치매)
        if night and dmin > L3.SAFEZONE_EXIT_M:
            return Detection("L3", AlertLevel.CAUTION, "wandering_night", 0.8, loc.ts,
                             {"dist_beyond_m": round(dmin, 0), "hour": hour})
        # 주간 이탈 = 외출 정보
        if dmin > L3.SAFEZONE_EXIT_M:
            return Detection("L3", AlertLevel.INFO, "safezone_exit", 0.5, loc.ts,
                             {"dist_beyond_m": round(dmin, 0)})
        return None


def _hour(ts: float) -> int:
    from datetime import datetime
    return datetime.fromtimestamp(ts).hour
