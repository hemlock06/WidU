# `train_fall_combined.py`

> 다중셋 결합 학습 — 일반화(특히 정밀도) robustness 향상.

## 무엇을 / 어떻게

cross-dataset 결과: 민감도는 전이되나 정밀도는 기기별로 하락 → 더 다양한 데이터로 학습.
  손목 모델 = WEDA + UMAFall(wrist)
  허리 모델 = SisFall + UMAFall(waist)
피험자 그룹에 데이터셋 접두사 → GroupKFold 가 자연히 dataset 혼합 폴드(일반화 인지 CV).
배포 경로(MODEL_PATH_WRIST/WAIST)에 덮어씀.

---
실행: `python scripts/train_fall_combined.py`
