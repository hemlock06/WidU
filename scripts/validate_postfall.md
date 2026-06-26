# `validate_postfall.py`

> 중간지평 '넘어진 뒤 미회복' 안전망 검증 (실 SisFall + 사후 정지 시뮬).

## 무엇을 / 어떻게

목적: L2(충격 분류)가 놓친 고령 낙상을, 충격 후 미회복(무활동)으로 잡는지 + 오탐.
방법: 실 파일을 충격 시점까지 먹인 뒤 '가만히 누움'을 시간 전진시켜 주입.
  - 고령 낙상: fall_unrecovered 발화율(=안전망 회수율)
  - 충격성 ADL(앉기 등 >ARM_G): 발화율(=오탐, 앉고 쉬면 잘못 울리나)
SisFall 녹화가 짧아 실제 미회복 FP율은 POC 필요 — 여기선 '정지 가정'하의 상한.

---
실행: `python scripts/validate_postfall.py`
