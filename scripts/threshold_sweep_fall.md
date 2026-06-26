# `threshold_sweep_fall.py`

> 임계 스윕 — 선택 구성(손목 C3, 허리 C1)에서 운영점 최적화.

## 무엇을 / 어떻게

폴드당 1회만 학습하고 저장된 확률에 여러 임계를 적용(효율적).
손목 C3(+SMM+고령ADL): 민감도 회복 임계 탐색(고령 FP 억제 유지).
허리 C1(레거시): 현 임계 적정성 확인.
산출 → artifacts/threshold_sweep_report.json

---
실행: `python scripts/threshold_sweep_fall.py`
