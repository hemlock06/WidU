# `eval_crossdataset.py`

> Cross-dataset 일반화 — 우리 모델이 다른 기기/인구에서도 유지되나.

## 무엇을 / 어떻게

지금까지: 손목=WEDA만, 허리=SisFall만 (각 단일셋). 단일셋 과적합이면 헤드라인 0.91이 허상.
측정:
  [손목] UMAFall-wrist 자체 CV(상한) vs WEDA모델→UMAFall-wrist(전이)
  [허리] UMAFall-waist 자체 CV(상한) vs SisFall모델→UMAFall-waist(전이)
전이 - 자체CV 하락폭 = 일반화 갭. (UMAFall 20Hz→50Hz 업샘플이라 rate도 갭에 포함)
결과 → artifacts/crossdataset.json

---
실행: `python scripts/eval_crossdataset.py`
