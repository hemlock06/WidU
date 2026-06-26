# `train_fall.py`

> 낙상 탐지 모델(L2) 학습 — SisFall 기반, 누수 없는 증강 파이프라인.

## 무엇을 / 어떻게

핵심 순서(중요):
  1) 윈도우 생성: 안티앨리어싱 리샘플(200→50Hz) + 일치 윈도우(extract_window).
  2) 피험자 단위 분할(GroupKFold) — 같은 사람 train/test 혼입 금지.
  3) **분할 이후, 학습 폴드에만** 증강(rotate/jitter/scale/time_warp).
  4) 특징추출은 학습/추론 동일 함수(extract_features).
최종 모델은 전체 실데이터 + 증강으로 학습해 저장(배포엔 홀드아웃 없음).

사용: python scripts/train_fall.py --root data/SisFall --n_aug 2

---
실행: `python scripts/train_fall.py`
