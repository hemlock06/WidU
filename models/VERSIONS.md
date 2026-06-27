# 모델 아티팩트 버전 기록 (재현성 — HANDOFF_ISSUES P1-5)

`*.joblib` 낙상 모델(scikit-learn RandomForest)은 직렬화 호환성이 scikit-learn
버전에 민감하다. 버전이 크게 바뀌면 역직렬화 시 `InconsistentVersionWarning`
또는 로드 실패가 발생할 수 있다.

## 검증된 호환 버전 (이 버전에서 경고 없이 로드·골든 일치 확인)

| 항목 | 값 |
|---|---|
| scikit-learn | 1.9.0 |
| joblib | 1.5.3 |
| numpy | 2.4.6 |
| Python | 3.11.15 |
| 검증 방법 | `joblib.load()` 시 InconsistentVersionWarning 없음 + `scripts/golden_check.py check` 11/11 일치 |
| 검증일 | 2026-06-28 |

## 모델 파일

| 파일 | 위치(source) | 데이터셋 | 비고 |
|---|---|---|---|
| `fall_rf.joblib` | 기본/폴백 | — | `L2.MODEL_PATH` |
| `fall_rf_wrist.joblib` | watch(손목) | WEDA | `L2.MODEL_PATH_WRIST` |
| `fall_rf_waist.joblib` | phone(허리/주머니) | SisFall | `L2.MODEL_PATH_WAIST` |

> 주의: 위 표의 scikit-learn 버전은 **로드 호환이 검증된** 버전이다. 모델을
> *학습*할 때 사용한 정확한 버전은 본 인수인계 시점에 메타로 남아 있지 않다
> (재학습 시 위 버전 또는 `requirements.lock` 으로 고정 후 본 표를 갱신할 것).
