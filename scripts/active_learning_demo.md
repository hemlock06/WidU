# `active_learning_demo.py`

> 능동학습 루프 데모 — 배포=실데이터 엔진.

## 무엇을 / 어떻게

루프: 이벤트 발생 → 센서 윈도우 캡처 → 사용자/가족 응답이 라벨 → 디스크 적재 →
      (누적분이 충분하면) train_fall_final 데이터에 합쳐 재학습 → 고령 recall 실데이터 개선.

API(serving): POST /users/<uid>/respond_ok(괜찮음=오경보) ·
              POST /users/<uid>/confirm_incident {is_fall} (가족 확인) · GET /collector/stats
활성: StreamProcessor(collect_data=True) 또는 env WIDU_COLLECT=1 (+ 사용자 동의). 기본 off=프라이버시.

---
실행: `python scripts/active_learning_demo.py`
