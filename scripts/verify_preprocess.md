# `verify_preprocess.py`

> 전처리·증강 10패스 자기재검증.

## 무엇을 / 어떻게

각 패스는 '제대로 됐는가 + 최선인가'를 코드로 단언한다. 하나라도 실패하면 종료코드 1.
실데이터 없이도 로직/물리 타당성은 전수 검증 가능(성능 수치는 실데이터·POC에서).

---
실행: `python scripts/verify_preprocess.py`
