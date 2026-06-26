# `optimize_fall_models.py`

> 낙상 모델 종합 최적화 — 모든 학습구성을 누수없이 비교해 최선 도출.

## 무엇을 / 어떻게

축(위치별 factorial):
  데이터  : 레거시(2소스) → +SmartFallMM young(3소스)
  고령ADL : 없음 → 추가(음성, 오탐 억제)
  증강    : 없음 → 있음(위치별 회전각, 학습폴드만)
평가(전부 누수없음):
  LODO        : 셋1개 통째로 빼고 학습→테스트 = 미지 출처 일반화(헤드라인)
  고령 FP     : 고령 피험자 GroupKFold = 미지 고령 일상 오탐율
  CV recall   : 풀링 피험자분할 = in-dist recall(하락 금지 가드)
선택 기준: LODO-F1↑ + 고령FP↓ + 젊은낙상 recall 유지. 임계 스윕으로 운영점.
산출 → artifacts/fall_optimization_report.json

---
실행: `python scripts/optimize_fall_models.py`
