# `eval_l4_resting_hr.py`

> L4(안정심박 추세) 실데이터 검증 — Stanford COVID Wearables(120명).

## 무엇을 / 어떻게

두 가지 정직한 측정(라벨 부재 → L1과 동일 방법론):
 (A) 실 오탐율: 실제 안정심박 일변동에 L4 CUSUM 상승추세 탐지 → person-month당 경보 수
     (대부분 person-day는 정상 → 스팸이면 높고, 특이적이면 낮다. FA 상한.)
 (B) 민감도/리드타임: 실 베이스라인 위에 감염형 상승(+Δbpm 램프)을 주입 →
     탐지율과 리드타임(증상 전 며칠 잡나) 측정. Δ 스윕.

산출 → artifacts/l4_resting_hr_report.json
일일 안정심박은 artifacts/l4_daily_rhr.json 에 캐시(재실행 가속).

---
실행: `python scripts/eval_l4_resting_hr.py`
