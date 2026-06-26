# `l1_fp_techniques.py`

> L1 오탐 억제 기법 스윕 — 검증된 기법을 PPG-DaLiA로 실측.

## 무엇을 / 어떻게

기법(웹리서치 근거):
  - 긴 지속시간(애플 HR 알림=10분, ICU 시간지연 50~67%↓)
  - 안정시에만(Stanford/애플 '비활동 시'): 활동 중 심박 무시 → 활동오류 오탐 제거
건강 피험자 → 모든 경보=오탐. 조합별 FP/시간 비교.

---
실행: `python scripts/l1_fp_techniques.py`
