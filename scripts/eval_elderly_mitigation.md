# `eval_elderly_mitigation.py`

> 고령 ADL 오탐(24%) 처방 검증 — '고령 ADL을 학습에 넣으면 줄어드나?'

## 무엇을 / 어떻게

사용자 질문의 핵심: 표적 데이터(고령 ADL)가 실제로 갭을 닫나?
정직한 설계: 고령 피험자를 분할(GroupKFold). 학습=젊은층 전부 + 고령ADL '학습 피험자',
테스트=완전히 빼둔 '테스트 피험자'의 고령 ADL 오탐율. (피험자 누수 없음)
 - 베이스라인: 젊은층만 학습 → 테스트 고령 오탐율
 - 처방: 젊은층 + 학습측 고령ADL → 테스트 고령 오탐율
처방이 낮추면=표적 고령데이터가 답. 안 낮추면=고령 '낙상'까지 필요(데이터로 못 사는 갭).
산출 → artifacts/elderly_mitigation_report.json

---
실행: `python scripts/eval_elderly_mitigation.py`
