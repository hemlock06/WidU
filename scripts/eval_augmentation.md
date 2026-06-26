# `eval_augmentation.py`

> 증강 efficacy A/B 검증 — 실 SisFall, 피험자분할 동일 폴드에서 증강有/無 비교.

## 무엇을 / 어떻게

11패스가 '정확성'을 봤다면, 이건 '증강이 실제로 일반화를 높이는가(efficacy)'를 본다.
같은 train/test 분할에서:
   A) 증강 없음(원본만)  vs  B) 학습셋만 증강
테스트셋은 양쪽 동일(원본만) → 공정 비교.

---
실행: `python scripts/eval_augmentation.py`
