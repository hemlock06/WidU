# `l1_activity_source_ab.py`

> L1 활동 소스 A/B — raw ACC 추정 vs '정확한 활동상태'(OS 활동인식 대리=라벨).

## 무엇을 / 어떻게

질문: 활동맥락을 raw 손목 ACC 로 추측하지 말고 OS 활동인식(CMMotionActivity/
Activity Recognition API)에서 받아오면 헛알람이 얼마나 주나?
PPG-DaLiA 활동 라벨 = '정확한 활동상태'의 대리(OS가 센서융합으로 주는 값에 해당).
건강 피험자 → 모든 경보=오탐. ACC맥락 vs 라벨맥락으로 같은 L1 돌려 FP/시간 비교.

---
실행: `python scripts/l1_activity_source_ab.py`
