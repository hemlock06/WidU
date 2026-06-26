# `validate.py`

> 종합 검증 하니스 — 각 계층 + 융합을 실제로 돌려 지표 산출.

## 무엇을 / 어떻게

데이터:
  - HR 이상: 합성 스트림에 이상 주입(공개셋은 라벨 부재 → 합성+POC로 보완하는 설계).
  - 낙상: 학습 모델 + 합성/실 SisFall 윈도우.
결과 → artifacts/validation_report.json

---
실행: `python scripts/validate.py`
