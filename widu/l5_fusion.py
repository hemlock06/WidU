"""L5 — 융합·등급·에스컬레이션.

여러 계층의 판단을 교차검증해 오경보를 억제하고 최종 등급/에스컬레이션을 정한다.
보호자 신뢰가 제품 생명 → 알림 예산 + 본인확인 + 자연어 근거.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

from .types import Detection, Assessment, AlertLevel, ActivityContext
from .config import L5

# 시나리오별 판단 유지 시간(초)
_TTL = {
    "L0": 90, "L1": 90, "L2": 600, "L3": 1800, "L4": 86400,
}

_SCENARIO_KO = {
    "flatline_arrest": "심박이 거의 잡히지 않습니다(실신·심정지 의심)",
    "bradycardia": "심박이 위험할 만큼 느립니다",
    "tachycardia": "심박이 위험할 만큼 빠릅니다",
    "resting_tachycardia": "안정 상태인데 심박이 비정상적으로 빠릅니다",
    "hr_high": "평소보다 심박이 크게 높습니다",
    "hr_low": "평소보다 심박이 크게 낮습니다",
    "fall_long_lie": "낙상 후 움직임이 없습니다",
    "fall_unrecovered": "넘어진 뒤 수 분째 움직임이 없습니다(미회복)",
    "fall_recovered": "낙상으로 보이는 충격이 감지됐습니다",
    "fall_confirmed": "낙상이 감지됐습니다",
    "fall_suspected": "낙상이 의심됩니다 — 괜찮으신지 확인이 필요합니다",
    "no_response_fall": "낙상 의심 후 응답이 없습니다",
    "immobility_12h": "장시간 움직임이 없습니다",
    "wandering_night": "야간에 안전구역을 벗어나 배회 중입니다",
    "safezone_exit": "안전구역을 벗어났습니다",
    "resting_hr_uptrend": "안정 심박이 며칠째 오르는 추세입니다(컨디션 저하 가능)",
    "spo2_low_trend": "산소포화도가 평소보다 낮은 추세입니다",
    "temp_uptrend": "체온이 오르는 추세입니다",
}


class FusionEngine:
    """사용자 1인의 융합 상태기계."""

    def __init__(self):
        self._active: Dict[Tuple[str, str], Tuple[Detection, float]] = {}
        self._alert_day: str = ""
        self._alert_count: int = 0

    def submit(self, det: Detection):
        ttl = _TTL.get(det.layer, 120)
        # 신호원(워치/폰)별로 따로 보관 → 교차검증 가능
        self._active[(det.layer, det.scenario, det.source)] = (det, det.ts + ttl)

    def _purge(self, ts: float):
        self._active = {k: v for k, v in self._active.items() if v[1] >= ts}

    def _budget_ok(self, ts: float) -> bool:
        day = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        if day != self._alert_day:
            self._alert_day, self._alert_count = day, 0
        return self._alert_count < L5.ALERT_BUDGET_PER_DAY

    def assess(self, ts: float, ctx: ActivityContext, no_contact: bool = False) -> Assessment:
        self._purge(ts)

        if no_contact and not self._active:
            return Assessment(ts, AlertLevel.NO_CONTACT, "워치 연결이 끊겼거나 미착용 상태입니다",
                              [], "in_app", ctx)

        dets: List[Detection] = [d for d, _ in self._active.values()]
        if not dets:
            return Assessment(ts, AlertLevel.NORMAL, "안정", [], "in_app", ctx)

        top = max(dets, key=lambda d: (d.level.rank, d.score))
        level = top.level
        scenarios = {d.scenario for d in dets}

        # --- 교차검증(오경보 억제 / 격상) --- #
        has_immobility = bool({"immobility_12h", "fall_long_lie"} & scenarios)
        only_hr_high = scenarios <= {"hr_high"}

        # 운동 맥락의 단독 고심박 → 격하(아티팩트/정상 빈맥)
        if only_hr_high and ctx == ActivityContext.ACTIVE and not has_immobility:
            level = AlertLevel.CAUTION if top.level == AlertLevel.EMERGENCY else top.level
        # 심박 이상 + 무활동 동시 → 위급 격상
        if ({"hr_high", "hr_low"} & scenarios) and has_immobility:
            level = AlertLevel.EMERGENCY

        # 낙상 교차검증: 워치+폰 두 신호원이 모두 → 고신뢰(보강만, 억제 안 함)
        fall_sources = {d.source for d in dets
                        if d.scenario in ("fall_long_lie", "fall_recovered",
                                          "fall_confirmed") and d.source}
        corroborated = len(fall_sources) >= 2
        if corroborated and {"fall_recovered"} & scenarios and not has_immobility:
            level = max(level, AlertLevel.CAUTION, key=lambda x: x.rank)

        # 단독 무활동(12h) 격하: 활동신호(걸음/가속도)가 거칠고 간헐결측이라
        # 단독 EMERGENCY는 실데이터 ~3.5회/년 오발(L3 무활동 실검증) → 알람피로.
        # 충격(fall_unrecovered)·이상심박 동반 시에만 위급, 단독은 CAUTION(본인확인·부드러운 push).
        if (level == AlertLevel.EMERGENCY and top.scenario == "immobility_12h"
                and not ({"hr_high", "hr_low", "bradycardia", "tachycardia",
                          "flatline_arrest", "fall_unrecovered", "fall_long_lie"}
                         & scenarios)):
            level = AlertLevel.CAUTION

        reason = self._compose_reason(dets, level)
        if corroborated:
            reason += " (워치+폰 교차확인)"
        escalation = self._escalate(level, scenarios, ts)
        return Assessment(ts, level, reason, sorted(
            dets, key=lambda d: -d.level.rank), escalation, ctx)

    def _escalate(self, level: AlertLevel, scenarios: set, ts: float) -> str:
        # 의심(낙상 회색지대)은 가족 알림 전에 본인 확인부터 — 무응답 시 no_response_fall 로 격상.
        if level == AlertLevel.CAUTION and ("fall_suspected" in scenarios) and \
                not ({"no_response_fall"} & scenarios):
            return "self_check"      # 워치 "괜찮으세요?" (예산 미소모)
        if level == AlertLevel.EMERGENCY:
            critical = bool({"flatline_arrest", "fall_long_lie", "bradycardia",
                             "tachycardia"} & scenarios)
            if self._budget_ok(ts):
                self._alert_count += 1
            return "auto_call" if critical else "guardian_push"
        if level == AlertLevel.CAUTION:
            if self._budget_ok(ts):
                self._alert_count += 1
                return "guardian_push"
            return "watch_haptic"
        if level == AlertLevel.INFO:
            return "in_app"
        return "in_app"

    @staticmethod
    def _compose_reason(dets: List[Detection], level: AlertLevel) -> str:
        parts = []
        for d in sorted(dets, key=lambda x: -x.level.rank):
            txt = _SCENARIO_KO.get(d.scenario, d.scenario)
            if txt not in parts:                 # 신호원 중복(워치/폰) 시 한 번만
                parts.append(txt)
            if len(parts) >= 3:
                break
        body = " · ".join(parts)
        prefix = {
            AlertLevel.EMERGENCY: "[위급] ",
            AlertLevel.CAUTION: "[주의] ",
            AlertLevel.INFO: "[정보] ",
            AlertLevel.NORMAL: "",
            AlertLevel.NO_CONTACT: "",
        }[level]
        return prefix + body
