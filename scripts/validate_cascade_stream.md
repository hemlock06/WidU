# `validate_cascade_stream.py`

> 캐스케이드(분류기-독립 hard-impact 경로) 스트리밍 검증 — 비용 vs 효익.

## 무엇을 / 어떻게

(1) FP(비용): 배포 손목모델로 실 WEDA ADL을 스트리밍 + 무활동 꼬리(최악조건) →
    fall_long_lie 오발율. 무활동 게이트가 ADL 큰충격(43%)을 거르는지.
(2) 복구(효익): WEDA '제외' 학습 손목모델로 WEDA 낙상 스트리밍 + 무활동 꼬리 →
    fall_long_lie 발화 중 impact_driven=False(분류기단독) vs True(캐스케이드 복구).
    한 번의 패스로 분류기-단독 recall과 캐스케이드 recall을 동시 측정.
산출 → artifacts/cascade_stream_report.json

---
실행: `python scripts/validate_cascade_stream.py`
