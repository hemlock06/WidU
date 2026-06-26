# `eval_cascade.py`

> 파형-무관 캐스케이드 효과 측정 — 분류기 미탐을 '충격+무활동'이 복구하나?

## 무엇을 / 어떻게

문제: L2가 proba>=th에만 의존 → 고령 소프트폴(분류기 약점)을 놓치면 후보조차 없음.
가설: hard impact(큰 SMV)는 분류기와 무관하게 낙상 신호. '충격 OR 분류기' 결합 recall 측정.
데이터: WEDA(손목, 소프트폴 F05~08=앉다가/실신=고령형) + SisFall(허리).
 - 분류기 recall vs (분류기 OR impact>=Hg) recall, 특히 소프트폴에서 복구량
 - ADL의 impact>=Hg 비율(=사후 무활동 게이트가 걸러야 할 잠재 FP)
 - hard 임계 후보 스윕
산출 → artifacts/cascade_report.json

---
실행: `python scripts/eval_cascade.py`
