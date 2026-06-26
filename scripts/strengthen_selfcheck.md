# `strengthen_selfcheck.py`

> self-check 임계(FALL_PROBA_SOFT) 최적화 — 시스템 recall ↔ 프롬프트 트레이드오프.

## 무엇을 / 어떻게

잔여 31%(저충격 소프트폴)를 줄이려 soft를 낮추면 recall↑·ADL 프롬프트↑.
과적합 방지: 단일셋 아니라 LODO(held-out 3셋) 평균으로 knee 선택.
빠른 해석모델(스트리밍 동등): 못 일어난 낙상(무활동+무응답) 시나리오에서
  caught = (proba>=soft → self-check 45초 무응답) OR (impact>=2.5g → L3/캐스케이드)
  prompt(UX) = ADL 중 proba>=soft 비율(=self_check 프롬프트)
산출 → artifacts/selfcheck_sweep_report.json

---
실행: `python scripts/strengthen_selfcheck.py`
