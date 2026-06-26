# `eval_l3_geolife.py`

> L3(위치/행동) 실데이터 검증 — GeoLife 1.3 실 GPS 궤적(182명).

## 무엇을 / 어떻게

GPS엔 '응급' 라벨이 없다 → recall이 아니라 결정적 기하의 'sanity·보정':
 1) staypoint 표준탐지(Li 2008, 반경 50m·체류 10분=우리 config) → 실 체류지 추출이 되나
 2) 최다 체류지 = 집(안전구역 proxy) 으로 두고 우리 지오펜스 로직 가동
 3) 측정: 사용자당 staypoint 수, 안전구역 이탈(INFO) 빈도, 야간배회(CAUTION) 빈도
    → 이탈이 '하루 몇 회' 수준의 상식적 빈도인가, 야간배회가 드물게(특이적) 뜨는가.
산출 → artifacts/l3_geolife_report.json

---
실행: `python scripts/eval_l3_geolife.py`
