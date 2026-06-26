# `eval_lodo.py`

> LODO(Leave-One-Dataset-Out) 낙상 일반화 검증 + 고령 ADL 오탐 probe.

## 무엇을 / 어떻게

비판원칙: '양' 아니라 '처음 보는 분포에 일반화되나'가 정직한 척도.
 위치별로 데이터셋 3개 중 1개를 통째로 빼고(held-out) 나머지로 학습 → 빼둔 셋 테스트.
 평균 = 새 출처(미지 기기/코호트)로의 기대 일반화. in-domain CV와의 격차 = '새 출처 페널티'.

 손목: WEDA · UMAFall(wrist) · SmartFallMM(young/watch)
 허리: SisFall · UMAFall(waist) · SmartFallMM(young/phone)

고령 probe: 손목 모델 → SmartFallMM old/watch(고령 ADL, 낙상無)의 오탐율 vs young ADL.
 (고령은 ADL만 → 낙상 recall 갭은 못 닫고, '고령 일상에 오발하는지'만 측정.)

산출 → artifacts/lodo_report.json

---
실행: `python scripts/eval_lodo.py`
