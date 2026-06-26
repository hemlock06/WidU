"""평가지표 — 탐지기 성능 + 운영 신뢰 지표.

설계 원칙(검증 전략)과 직결:
  - 민감도(놓치면 안 됨) · 특이도 · 정밀도
  - 도달시간 TTA(골든타임)
  - 오경보/사용자·일 (보호자 신뢰)
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

import numpy as np


@dataclass
class ClassMetrics:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def sensitivity(self) -> float:  # recall
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 0.0

    @property
    def specificity(self) -> float:
        return self.tn / (self.tn + self.fp) if (self.tn + self.fp) else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.sensitivity
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def summary(self) -> Dict[str, float]:
        return {
            "sensitivity": round(self.sensitivity, 4),
            "specificity": round(self.specificity, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            **{k: v for k, v in asdict(self).items()},
        }


def binary_metrics(y_true: Sequence[int], y_pred: Sequence[int]) -> ClassMetrics:
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    return ClassMetrics(tp, fp, tn, fn)


def time_to_alert(event_ts: float, alert_ts: Optional[float]) -> Optional[float]:
    """이벤트 발생부터 경보까지 초. 미탐이면 None."""
    if alert_ts is None:
        return None
    return alert_ts - event_ts


def false_alarms_per_user_day(n_false: int, n_users: int, n_days: float) -> float:
    denom = max(n_users * n_days, 1e-9)
    return n_false / denom


def windowed_event_metrics(
    pred_alert_idx: List[int],
    event_spans: List[tuple],
    n: int,
    tolerance: int = 5,
) -> Dict[str, float]:
    """이벤트 단위 평가: 각 이벤트 구간 근처에서 경보가 떴는지.

    event_spans: [(start,end), ...], tolerance: 허용 지연(샘플).
    """
    detected = 0
    for (s, e) in event_spans:
        if any(s - tolerance <= p <= e + tolerance for p in pred_alert_idx):
            detected += 1
    # 이벤트 밖 경보 = 오경보
    def in_event(p):
        return any(s - tolerance <= p <= e + tolerance for (s, e) in event_spans)
    false = sum(1 for p in pred_alert_idx if not in_event(p))
    n_ev = max(len(event_spans), 1)
    return {
        "event_recall": round(detected / n_ev, 4),
        "events_detected": detected,
        "events_total": len(event_spans),
        "false_alerts": false,
    }
