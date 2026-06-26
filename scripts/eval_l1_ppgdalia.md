# `eval_l1_ppgdalia.py`

> L1(개인화 심박) 실데이터 검증 — PPG-DaLiA(실 손목 HR + 활동).

## 무엇을 / 어떻게

핵심: 피험자는 건강한 사람들이 운동/일상 → 라벨된 '심박 이상' 없음.
따라서 여기서 뜨는 모든 경보 = 오탐(FP). 이걸로 L1의 실세계 오탐률을 측정.
A/B(맥락게이팅의 가치):
  - gated  : 활동맥락 조건부 개인 기준선(우리 L1) — 운동 중 고심박을 정상으로.
  - naive  : 고정 임계(bpm>100 지속) — 맥락 무시(GitHub MA 레포 류).
또한 ① 맥락별 HR 분리(REST<ACTIVE) ② ACC추정맥락 vs 활동라벨 일치 검증.
결과 → artifacts/l1_ppgdalia.json

---
실행: `python scripts/eval_l1_ppgdalia.py`
