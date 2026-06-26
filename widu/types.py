"""공통 데이터 계약 — 모든 계층이 공유하는 입력/출력 타입.

WIDYU 실측 데이터 계약(Confluence '건강 데이터 수집 가능성 조사')에 맞춤:
  - 심박수: 1Hz, bpm(float) + accuracy 플래그
  - 가속도/자이로: 50~200Hz, acc_xyz / gy_xyz (워치 또는 폰 BLE)
  - 위치: 이벤트성 (lat/lon)
  - SpO2 / 체온: 기록형(실시간 불가) → RecordSample
타임스탬프는 모두 절대 epoch 초(float)로 정규화한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


# --------------------------------------------------------------------------- #
# 열거형
# --------------------------------------------------------------------------- #
class Accuracy(str, Enum):
    """Health Connect / HealthKit 의 심박 센서 정확도 플래그."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NO_CONTACT = "NO_CONTACT"      # 미착용 — 경보 아님, '연결 불가' 상태로
    UNRELIABLE = "UNRELIABLE"
    UNKNOWN = "UNKNOWN"

    @property
    def is_trustworthy(self) -> bool:
        return self in (Accuracy.HIGH, Accuracy.MEDIUM)


class ActivityContext(str, Enum):
    """가속도/걸음에서 추정한 활동 맥락 — HR 정상범위를 조건부로 만든다."""
    SLEEP = "SLEEP"
    REST = "REST"
    LOW = "LOW"        # 저활동(가벼운 가사 등)
    ACTIVE = "ACTIVE"  # 운동/빠른 보행
    UNKNOWN = "UNKNOWN"


class AlertLevel(str, Enum):
    """UI 3-상태(안정/주의/위급) + 미착용 + 정보."""
    NORMAL = "NORMAL"        # 안정
    INFO = "INFO"            # 정보(소프트 인사이트)
    CAUTION = "CAUTION"      # 주의
    EMERGENCY = "EMERGENCY"  # 위급
    NO_CONTACT = "NO_CONTACT"  # 연결 불가/미착용

    @property
    def rank(self) -> int:
        return {
            AlertLevel.NO_CONTACT: -1,
            AlertLevel.NORMAL: 0,
            AlertLevel.INFO: 1,
            AlertLevel.CAUTION: 2,
            AlertLevel.EMERGENCY: 3,
        }[self]


class RecordKind(str, Enum):
    SPO2 = "SPO2"          # 0.0~1.0 (Health 패키지 규약)
    TEMP = "TEMP"          # °C
    HRV = "HRV"            # ms (SDNN)
    SLEEP = "SLEEP"        # 시간(h)
    STEPS = "STEPS"        # 누적 걸음
    RESTING_HR = "RESTING_HR"  # bpm (일 대표값)


# --------------------------------------------------------------------------- #
# 입력 샘플
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class HRSample:
    ts: float                 # epoch sec
    bpm: float
    accuracy: Accuracy = Accuracy.UNKNOWN


@dataclass(slots=True)
class IMUSample:
    ts: float
    ax: float                 # g (중력 단위로 정규화)
    ay: float
    az: float
    gx: float = 0.0           # rad/s
    gy: float = 0.0
    gz: float = 0.0
    accuracy: int = 3         # 3=High 2=Med 1=Low
    source: str = "watch"     # "watch"(손목·상시) | "phone"(주머니·간헐, 신체중심)


@dataclass(slots=True)
class LocSample:
    ts: float
    lat: float
    lon: float
    speed: Optional[float] = None  # m/s (있으면)


@dataclass(slots=True)
class RecordSample:
    ts: float
    kind: RecordKind
    value: float


# --------------------------------------------------------------------------- #
# 출력
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Detection:
    """한 계층이 낸 판단."""
    layer: str                # "L0".."L4"
    level: AlertLevel
    scenario: str             # 시나리오 코드/이름 (예: "tachy", "fall", "immobility")
    score: float = 0.0        # 0~1 신뢰도/이상도
    ts: float = 0.0
    evidence: Dict[str, Any] = field(default_factory=dict)
    source: str = ""          # 신호원(워치/폰) — 동일 시나리오의 교차검증 키


@dataclass(slots=True)
class Assessment:
    """L5 융합 후 사용자에게 내려가는 최종 판단."""
    ts: float
    level: AlertLevel
    reason_ko: str                       # 보호자용 자연어 근거
    detections: list = field(default_factory=list)   # list[Detection]
    escalation: str = "in_app"           # in_app|watch_haptic|guardian_push|auto_call
    context: ActivityContext = ActivityContext.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "level": self.level.value,
            "reason": self.reason_ko,
            "escalation": self.escalation,
            "context": self.context.value,
            "detections": [
                {"layer": d.layer, "level": d.level.value, "scenario": d.scenario,
                 "source": d.source, "score": round(d.score, 3), "evidence": d.evidence}
                for d in self.detections
            ],
        }
