# `eval_wrist.py`

> 손목(우리 실제 기기) 낙상 검증 — WEDA-FALL(손목·고령·50Hz).

## 무엇을 / 어떻게

지금까지는 SisFall=허리(폰 대용)뿐 → 손목 미검증이 핵심 한계였음.
WEDA로 실측:
  A) 손목 자체 CV: 우리 기기 분포에서의 진짜 낙상/고령/소프트폴 recall.
  B) 일반화 갭: 허리(SisFall) 학습모델 → 손목(WEDA) 적용 시 성능 저하.
결과 → artifacts/wrist_eval.json

---
실행: `python scripts/eval_wrist.py`
