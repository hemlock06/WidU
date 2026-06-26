"""WidU — 독거 고령자 실시간 위급상황 탐지 AI.

5계층 파이프라인:
    L0 결정적 안전룰  (widu.l0_safety)
    L1 개인화 심박     (widu.l1_hr)
    L2 낙상 탐지       (widu.l2_fall)
    L3 행동·위치       (widu.l3_behavior)
    L4 느린 추세       (widu.l4_trend)
    L5 융합·에스컬레이션 (widu.l5_fusion)

진입점: widu.pipeline.StreamProcessor
"""

__version__ = "0.1.0"

from . import config  # noqa: F401
from .types import (  # noqa: F401
    Accuracy,
    ActivityContext,
    AlertLevel,
    RecordKind,
    HRSample,
    IMUSample,
    LocSample,
    RecordSample,
    Detection,
    Assessment,
)
