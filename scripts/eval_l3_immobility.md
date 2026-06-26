# `eval_l3_immobility.py`

> L3 무활동(12h) + 공백리셋 실데이터 검증 — Stanford 걸음 데이터(120명, 수개월).

## 무엇을 / 어떻게

검증 대상(v0.3 버그픽스): 실제 기기-off 공백(미착용/충전/수면)을 '무활동'으로
오인해 12h 경보를 남발하지 않는가. 진짜 위험(착용중 12h 부동)만 잡는가.

방법: 분당 걸음 → 10분 빈 활동맥락. 걸음>0=이동(active), 걸음0(데이터있음)=정지(rest),
데이터없음=공백(샘플 미도착=update_activity 미호출) → 다음 샘플서 공백리셋 발동.
측정: 12h 무활동 경보 총수. 실 인구에선 ≈0이어야(깨어있으면 12h내 움직임 + 공백리셋).
산출 → artifacts/l3_immobility_report.json

---
실행: `python scripts/eval_l3_immobility.py`
