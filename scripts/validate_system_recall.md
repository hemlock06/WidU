# `validate_system_recall.py`

> 시스템 단위 recall — '낙상을 8초에 분류했나'가 아니라 '결국 가족이 알았나'.

## 무엇을 / 어떻게

분류기가 못 맞혀도(held-out 모델=WEDA 미학습 → 일부 미탐) 사후 무활동+무응답이면
방어층 합집합이 잡는지 측정: 캐스케이드(센충격+8s) · self-check(45s 무응답) ·
L3 미회복(충격+3분) · 분류기(proba≥th). 어느 층이 며칠/몇초에 잡는지 + 시스템 recall.

데이터: WEDA 낙상(실 충격) + 사후 무활동 꼬리 주입('넘어져 못 일어남', 응답 없음).
산출 → artifacts/system_recall_report.json

---
실행: `python scripts/validate_system_recall.py`
