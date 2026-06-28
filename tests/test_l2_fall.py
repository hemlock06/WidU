"""L2(낙상) 단위 테스트 — 특징 계약 + 캐스케이드 안전망만 보수적으로 박제.

핵심 계약(widu/l2_fall.py):
  - 특징 벡터 길이 = len(FALL_FEATURES) = 23 (학습/추론 공유 순서 계약).
  - 파형-무관 안전망: 매우 센 충격(IMPACT_HARD_G=3.0) + 사후 무활동
    → 분류기 proba 와 무관하게 fall_long_lie(EMERGENCY).
  - 평범한 안정 신호에는 발화하지 않는다.
"""
from __future__ import annotations

import numpy as np
import pytest

from widu.l2_fall import (FALL_FEATURES, extract_features, FallModel,
                          FallDetector)
from widu.types import IMUSample, AlertLevel
from widu.config import L2


def test_feature_contract_length():
    assert len(FALL_FEATURES) == 23


def test_extract_features_shape_deterministic():
    rng = np.random.default_rng(42)
    win = rng.normal(0, 0.3, (100, 6))
    win[50, :3] += [3.0, 3.0, 3.0]
    feat = extract_features(win, L2.FS)
    assert feat.shape == (23,)
    assert np.all(np.isfinite(feat))
    # 결정성: 동일 입력 → 동일 출력
    feat2 = extract_features(win, L2.FS)
    assert np.allclose(feat, feat2)


def test_heuristic_fallback_in_range():
    # 모델 파일이 없으면 휴리스틱 폴백 — proba 는 [0,1] 범위
    fm = FallModel(path="__no_such_model__.joblib")
    assert fm.trained is False
    rng = np.random.default_rng(0)
    win = rng.normal(0, 0.3, (100, 6))
    win[50, :3] += [4.0, 0.0, 0.0]
    feat = extract_features(win, L2.FS)
    p = fm.fall_proba(feat)
    assert 0.0 <= p <= 1.0


def test_hard_impact_then_immobile_fires_long_lie():
    """센 충격(>=3g) 후 사후 무활동 → fall_long_lie EMERGENCY(분류기 무관 안전망).

    golden_check 의 fall_hard_immobile 케이스를 FallDetector 단위로 재현.
    """
    fd = FallDetector(source="watch")
    t, dt = 0.0, 1.0 / 50
    # 안정(착용·정지) — 윈도우 채우기
    for _ in range(120):
        fd.update(IMUSample(t, 0.0, 0.0, 1.0)); t += dt
    # 강한 충격(smv≈4.9g > IMPACT_HARD_G 3.0)
    for _ in range(3):
        fd.update(IMUSample(t, 4.0, 2.0, 2.0)); t += dt
    # 사후 장기 무활동
    fired = None
    for _ in range(500):
        d = fd.update(IMUSample(t, 0.0, 0.0, 1.001)); t += dt
        if d is not None and d.level == AlertLevel.EMERGENCY:
            fired = d.scenario
            break
    assert fired == "fall_long_lie"


def test_quiet_rest_no_fall():
    fd = FallDetector(source="watch")
    t, dt = 0.0, 1.0 / 50
    fired = None
    for _ in range(600):
        d = fd.update(IMUSample(t, 0.0, 0.0, 1.0)); t += dt
        if d is not None:
            fired = d.scenario
    assert fired is None


def test_position_threshold_wiring():
    # 위치별 임계 배선(손목 0.30 / 허리 0.40) 회귀 가드
    assert FallDetector(source="watch").proba_th == 0.30
    assert FallDetector(source="phone").proba_th == 0.40
    assert L2.IMPACT_HARD_G == 3.0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
