# `train_fall_final.py`

> 최종 배포 낙상모델 재학습 — 최적화에서 고른 승리 구성으로 전체 데이터 학습.

## 무엇을 / 어떻게

배포 모델은 holdout 없이 가용 전 데이터로 학습(일반화 추정치는 LODO가 이미 제공).
승리 구성(기본): 모든 젊은 소스(낙상+ADL) + 고령 ADL(음성) + 증강(위치별 회전각).
기존 models/*.joblib 은 .bak 백업 후 덮어씀. 학습 후 피험자분할 CV sanity 출력.

사용: python scripts/train_fall_final.py --position wrist --smm --elderly --aug

---
실행: `python scripts/train_fall_final.py`
