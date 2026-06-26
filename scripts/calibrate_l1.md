# `calibrate_l1.py`

> 활동맥락 임계 보정 — 손목 ACC SMA → {REST/LOW/ACTIVE} 임계를 PPG-DaLiA 라벨로 최적화.

## 무엇을 / 어떻게

L1 오탐의 주원인 = 활동 오추정(0.68). SMA 임계가 E4 손목 ACC에 안 맞을 수 있음.
라벨(휴식/저활동/운동) 대비 3-class 일치를 최대화하는 SMA_REST/SMA_LOW 를 그리드 탐색.
출력: 권장 임계 + 보정 전/후 일치도. (config 갱신은 사람이 판단)

---
실행: `python scripts/calibrate_l1.py`
