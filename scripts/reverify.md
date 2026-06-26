# `reverify.py`

> 10라운드 재검증 — 주요 페이즈(실데이터 낙상 검증) 통과 전 최종 점검.

## 무엇을 / 어떻게

'문제 없었는가 + 이게 최선인가'를 10개 상이 관점으로 실제 코드로 단언한다.
SisFall을 1회 로드 후 OOF(out-of-fold) 예측을 재사용해 여러 라운드를 검증.
결과 → artifacts/reverify_report.json

---
실행: `python scripts/reverify.py`
