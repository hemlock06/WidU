# `strengthen_wrist_features.py`

> 손목 강화 2단계 — 특징 공학. 분류기로 안 오르면 더 변별력 있는 특징을 시험.

## 무엇을 / 어떻게

추가 특징(낙상 vs 손동작 변별, 스케일/회전 강건 지향):
  - SMV 첨도·왜도(충격 스파이크→고첨도)
  - 스펙트럼: 지배주파수, 1~3Hz/3~8Hz 대역에너지비(손동작=율동적 저주파, 낙상=충격성 광대역)
  - 피크 수(손동작=다중피크, 낙상=단일 큰충격)
  - 사후정착비(피크 후/전 에너지)·자기상관 피크(주기성=ADL)
  - gyro-accel 상관
LODO로 base 대비 향상 여부 정직 비교(RF·ExtraTrees). 안 오르면 데이터 한계 확정.
산출 → artifacts/wrist_features_report.json

---
실행: `python scripts/strengthen_wrist_features.py`
