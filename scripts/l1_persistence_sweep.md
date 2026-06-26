# `l1_persistence_sweep.py`

> L1 지속시간 최적화 — 속도 vs 오탐 트레이드오프.

## 무엇을 / 어떻게

지속시간↑ = 오탐↓ 이지만 알림 지연↑(응급엔 느림).
→ 최선 = '오탐을 0(또는 허용)으로 유지하는 가장 짧은 지속시간'(가장 빠른 알림).
rest_only=True 고정, 지속시간 스윕. PPG-DaLiA(건강자→모든경보=오탐).

---
실행: `python scripts/l1_persistence_sweep.py`
