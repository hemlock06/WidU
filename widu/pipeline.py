"""StreamProcessor — 5계층을 묶는 진입점.

사용자별 상태를 보유하고, 들어오는 신호(HR/IMU/위치/기록)를 해당 계층으로 라우팅,
L5 융합 결과(Assessment)를 돌려준다. 서빙 API(serving/api.py)가 이를 감싼다.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .types import (HRSample, IMUSample, LocSample, RecordSample,
                    Assessment, AlertLevel, Detection)
from .gating import quality_gate, ActivityEstimator
from .l0_safety import L0Safety
from .l1_hr import PersonalHRModel
from .l2_fall import FallDetector, FallModel
from .l3_behavior import BehaviorMonitor
from .l4_trend import TrendMonitor
from .l5_fusion import FusionEngine
from .datalog import ActiveLearningCollector

# 능동학습 캡처 대상(라벨 가치 있는 이벤트) + 링버퍼 길이
_CAPTURE_SCENARIOS = {"fall_suspected", "fall_recovered", "fall_long_lie",
                      "fall_confirmed", "fall_unrecovered"}
_IMU_BUF_N = 500   # 10초 @50Hz — 이벤트 전후 맥락


@dataclass
class UserState:
    activity: ActivityEstimator = field(default_factory=ActivityEstimator)
    l0: L0Safety = field(default_factory=L0Safety)
    l1: PersonalHRModel = field(default_factory=PersonalHRModel)
    l2: Dict[str, FallDetector] = field(default_factory=dict)   # source -> 낙상 탐지기
    l3: BehaviorMonitor = field(default_factory=BehaviorMonitor)
    l4: TrendMonitor = field(default_factory=TrendMonitor)
    fusion: FusionEngine = field(default_factory=FusionEngine)
    last_ts: float = 0.0
    no_contact: bool = False
    last_seen: Dict[str, float] = field(default_factory=dict)   # source -> 마지막 IMU ts
    pending_check: Optional[tuple] = None   # (armed_ts, reason) — 능동 확인 대기 중
    imu_buffer: deque = field(default_factory=lambda: deque(maxlen=_IMU_BUF_N))  # 능동학습 맥락
    pending_event_id: Optional[str] = None  # 라벨 대기 중인 수집 이벤트


class StreamProcessor:
    # 워치=상시 착용(주), 폰=간헐(보강). 두 IMU는 독립 위치라 별도 탐지기.
    # 기기 가용성: 워치 있으면 워치가 wear, 없으면 폰으로 자동 전환(폰-단독 폴백).
    WEAR_SOURCE = "watch"
    WEAR_GAP_SEC = 60.0           # 이 시간 내 신호 없으면 그 기기는 '없음'으로 간주

    def __init__(self, shared_fall_model: Optional[FallModel] = None,
                 collect_data: bool = False):
        self._users: Dict[str, UserState] = {}
        # 위치별 모델 공유(사용자 간). 강제 주입 시 모든 source 에 동일 모델.
        self._forced_model = shared_fall_model
        self._models: Dict[str, FallModel] = {}
        # 능동학습 수집기(동의 시에만 enabled). 이벤트+응답라벨 → 실데이터 누적.
        from .config import DATA_DIR
        self.collector = ActiveLearningCollector(DATA_DIR / "active_learning",
                                                 enabled=collect_data)

    def _model_for(self, source: str) -> FallModel:
        if self._forced_model is not None:
            return self._forced_model
        if source not in self._models:
            from .config import L2
            m = FallModel(L2.MODEL_BY_SOURCE.get(source, L2.MODEL_PATH))
            if not m.trained:                     # 위치별 모델 없으면 기본 폴백
                m = FallModel(L2.MODEL_PATH)
            self._models[source] = m
        return self._models[source]

    def _state(self, user: str) -> UserState:
        if user not in self._users:
            self._users[user] = UserState()
        return self._users[user]

    def _fall(self, st: UserState, source: str) -> FallDetector:
        if source not in st.l2:
            st.l2[source] = FallDetector(model=self._model_for(source), source=source)
        return st.l2[source]

    def _wear_source(self, st: UserState, ts: float) -> str:
        """활동/무활동을 누구 기준으로? 워치 있으면 워치, 없으면 폰(폰-단독 폴백)."""
        w = st.last_seen.get("watch")
        if w is not None and ts - w <= self.WEAR_GAP_SEC:
            return "watch"
        p = st.last_seen.get("phone")
        if p is not None and ts - p <= self.WEAR_GAP_SEC:
            return "phone"
        return self.WEAR_SOURCE

    def set_safe_zones(self, user: str, zones: List[Tuple[float, float, float]]):
        self._state(user).l3.set_safe_zones(zones)

    # ----------------------------- 입력 ----------------------------- #
    def ingest_hr(self, user: str, hr: HRSample) -> Assessment:
        st = self._state(user)
        st.last_ts = hr.ts
        use, no_contact = quality_gate(hr)
        st.no_contact = no_contact
        if use:
            ctx = st.activity.context
            artifact = st.activity.is_motion_artifact_risk()
            for det in (st.l0.update(hr, ctx), st.l1.update(hr, ctx, artifact)):
                if det:
                    st.fusion.submit(det)
        return st.fusion.assess(hr.ts, st.activity.context, st.no_contact)

    def ingest_imu(self, user: str, s: IMUSample) -> Optional[Assessment]:
        st = self._state(user)
        st.last_ts = s.ts
        st.last_seen[s.source] = s.ts
        if self.collector.enabled:
            st.imu_buffer.append((s.ax, s.ay, s.az, s.gx, s.gy, s.gz))
        dets = []
        # 낙상은 신호원별 탐지기(워치/폰) — 위치가 달라 독립
        fd = self._fall(st, s.source)
        det_fall = fd.update(s)
        # 충격 발생 시 L3 '넘어진 뒤 미회복' 감시 무장(워치/폰 공통)
        if fd.impact_fired:
            st.l3.note_impact(s.ts, fd.last_impact_g)
        # 활동맥락·무활동은 '착용기기' 기준 — 워치 우선, 없으면 폰(폰-단독 폴백)
        if s.source == self._wear_source(st, s.ts):
            ctx = st.activity.update(s)
            dets.append(st.l3.update_activity(ctx, s.ts))
        else:
            ctx = st.activity.context
        dets.append(det_fall)
        # 능동 확인(self-check) 무장: 의심/회복 → 본인 확인 대기. 위급 낙상은 즉시 격상(확인 불필요).
        for det in dets:
            if det and det.scenario in ("fall_suspected", "fall_recovered"):
                st.pending_check = (s.ts, det.scenario)
            elif det and det.scenario in ("fall_long_lie", "fall_confirmed"):
                st.pending_check = None
        fired = False
        for det in dets:
            if det:
                st.fusion.submit(det)
                fired = True
                # 능동학습: 라벨 가치 있는 이벤트면 직전 IMU 윈도우 스냅샷(라벨 대기)
                if self.collector.enabled and det.scenario in _CAPTURE_SCENARIOS:
                    eid = f"{user}-{int(s.ts * 1000)}"
                    win = np.array(st.imu_buffer, float)
                    if self.collector.capture(eid, user, win,
                                              {"event_ts": round(s.ts, 3), "reason": det.scenario,
                                               "source": getattr(det, "source", s.source) or s.source,
                                               "fs": 50}):
                        st.pending_event_id = eid
        # 무응답 타임아웃(매 ingest 검사) → no_response_fall 격상
        to = self._self_check_timeout(st, s.ts)
        if to is not None:
            st.fusion.submit(to)
            return st.fusion.assess(s.ts, ctx, st.no_contact)
        return st.fusion.assess(s.ts, ctx, st.no_contact) if fired else None

    def _self_check_timeout(self, st: UserState, ts: float) -> Optional[Detection]:
        """확인 대기 중 SELF_CHECK_SEC 무응답 → 무응답 격상 Detection."""
        if st.pending_check is None:
            return None
        from .config import L5
        armed_ts, reason = st.pending_check
        if ts - armed_ts >= L5.SELF_CHECK_SEC:
            st.pending_check = None
            return Detection("L5", AlertLevel.EMERGENCY, "no_response_fall", 0.9, ts,
                             {"since_s": round(ts - armed_ts), "from": reason})
        return None

    def respond_ok(self, user: str, ts: float) -> Assessment:
        """사용자가 '괜찮다'고 응답 → 확인 대기 해제 + 능동학습 라벨=오경보."""
        st = self._state(user)
        st.pending_check = None
        if st.pending_event_id is not None:
            self.collector.label(st.pending_event_id, "false_alarm", by="user")
            st.pending_event_id = None
        return st.fusion.assess(ts, st.activity.context, st.no_contact)

    def confirm_incident(self, user: str, is_fall: bool, by: str = "guardian") -> Optional[str]:
        """가족/사용자가 사후 확인('진짜 낙상' 또는 '오경보') → 능동학습 라벨 적재.
        반환: 적재된 sample_id(없으면 None). 배포 후 실데이터(고령 포함) 누적의 핵심 훅."""
        st = self._state(user)
        if st.pending_event_id is None:
            return None
        sid = self.collector.label(st.pending_event_id,
                                   "fall" if is_fall else "false_alarm", by=by)
        st.pending_event_id = None
        return sid

    def ingest_fall_event(self, user: str, ts: float, source: str = "watch",
                          confidence: float = 0.95) -> Assessment:
        """네이티브 낙상 이벤트 입력(삼성 Health Services FALL_DETECTED / Wear OS 등).

        워치가 자체 검출한 낙상을 그대로 수용(우리 IMU 분류 불필요). 같은 융합·교차검증·
        미회복 안전망이 적용된다. 폰(우리 모델)과 동시 감지 시 L5 교차확인.

        ★현황(2026-06-30 앱 repo GB-able/WIDYU-widyu 코드 직접 확인): 이 네이티브 경로는
        **아직 라이브 아님**. 현 워치=Wear OS(심박만 수집, IMU·낙상 코드 전무), 애플워치
        앱은 미완(WIP). 디바이스 IMU 파이프라인 자체가 계획 단계 → 현 시점 L2의 라이브
        데이터 소스 없음. 향후 네이티브 낙상 가용 시: iOS=애플 공식 CMFallDetectionManager
        (엔타이틀먼트 com.apple.developer.health.fall-detection 승인 필요), 안드=오픈 API
        없음(삼성 Health SDK 파트너십)→안드는 우리 L2가 주력. 어느 쪽이든 native 승인·가용을
        가정하지 말 것(우리 L2가 안전망).
        """
        st = self._state(user)
        st.last_ts = ts
        st.last_seen[source] = ts
        st.fusion.submit(Detection("L2", AlertLevel.EMERGENCY, "fall_confirmed",
                                   confidence, ts, {"native": True, "source": source},
                                   source=source))
        st.l3.note_impact(ts, 99.0)   # 네이티브 낙상 = 강한 충격으로 간주 → 미회복 감시 무장
        return st.fusion.assess(ts, st.activity.context, st.no_contact)

    def ingest_location(self, user: str, loc: LocSample) -> Optional[Assessment]:
        st = self._state(user)
        st.last_ts = loc.ts
        det = st.l3.update_location(loc)
        if det:
            st.fusion.submit(det)
            return st.fusion.assess(loc.ts, st.activity.context, st.no_contact)
        return None

    def ingest_record(self, user: str, rec: RecordSample) -> Optional[Assessment]:
        st = self._state(user)
        det = st.l4.update(rec)
        if det:
            st.fusion.submit(det)
            return st.fusion.assess(rec.ts, st.activity.context, st.no_contact)
        return None

    # ----------------------------- 상태 ----------------------------- #
    def status(self, user: str) -> Assessment:
        st = self._state(user)
        return st.fusion.assess(st.last_ts, st.activity.context, st.no_contact)
