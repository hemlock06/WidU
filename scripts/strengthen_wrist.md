# `strengthen_wrist.py`

> 손목 낙상모델 강화 — 데이터 고정(C3), 모델/정규화 변형을 LODO로 정직 비교.

## 무엇을 / 어떻게

손목 LODO F1 0.71~0.74가 약점(교차기기 일반화). 특징은 한 번만 추출(캐시),
분류기·정규화·하이퍼파라미터만 바꿔 LODO F1 + 고령 FP(@th 0.30) 비교.
'강화'를 주장하려면 LODO(미지 출처)에서 올라야 함 — in-domain 부풀림 금지.

변형:
  M0 RF-300            (현 배포 baseline)
  M1 RF-reg            (min_samples_leaf=4, max_features=sqrt — 과적합 억제)
  M2 ExtraTrees-400
  M3 HistGradientBoost
  M4 RF + isotonic 보정 (CalibratedClassifierCV)
  M5 RF-300 + 표준화    (StandardScaler — 교차기기 스케일 차 완화)
  M6 RF-300 + 로버스트  (RobustScaler — 이상치/기기차 강건)
산출 → artifacts/wrist_strengthen_report.json

---
실행: `python scripts/strengthen_wrist.py`
