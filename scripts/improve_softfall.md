# `improve_softfall.py`

> 고령 낙상 recall 개선 — 진단 + 소프트폴 피처 A/B (실 SisFall).

## 무엇을 / 어떻게

가설: 고령 소프트폴(천천히 주저앉음)은 충격 피처상 ADL과 닮아 분류기가 놓침.
1) 진단: 고령 미탐이 '트리거(충격 부재)'냐 '분류(피처 부족)'냐 분해.
2) A/B: 기존 14피처 vs +소프트폴 피처. 고령 recall 개선폭 실측(피험자분할 OOF, 임계 0.4).
효과 있으면 widu.l2_fall.extract_features에 반영·재학습·재검증.

---
실행: `python scripts/improve_softfall.py`
