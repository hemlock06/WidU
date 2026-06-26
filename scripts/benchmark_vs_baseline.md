# `benchmark_vs_baseline.py`

> 머리맞대 벤치마크 — WIDYU-ai(원본) vs WidU(L0+L1).

## 무엇을 / 어떻게

원본(app.py 그대로): 최근 15개 HR의 MA±2σ 밖(국소이상치) AND 고정 band(≥100 or ≤80) → 1.
  ★상태없음·맥락없음·HR만. 두 조건 AND → 점진 악화는 MA가 추종해 outlier 실패 = 미탐 예상.
WidU: L0(임상 하드바운드<40/>150/<25 + 안정맥락>130, 지속) + L1(개인 baseline·맥락·3분지속·안정시).

측정:
 (1) 오경보율: PPG-DaLiA 실데이터(건강 15명) → 두 시스템 알람 에피소드/시간(건강=전부 오탐).
 (2) 응급 탐지: 합성 스트림에 급성/점진 서맥·빈맥·안정빈맥 주입 → 탐지여부·지연.
산출 → artifacts/benchmark_vs_baseline.json

---
실행: `python scripts/benchmark_vs_baseline.py`
