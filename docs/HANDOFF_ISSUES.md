# WidU 인수인계 개선 과제 (P0/P1/P2)

> 인수인계 시점(`handoff-prep`)에 **코드를 읽고 검증한 사실**만 기록. 추측 배제.
> 각 항목: **위치 · 현상(검증) · 이유 · 제안**. 우선순위는 *프로덕션 배포 영향* 기준.
> P0=배포 차단 / P1=프로덕션 전 필수 / P2=정리·문서.
>
> 본 브랜치는 **기존 소스 로직을 수정하지 않았다**(추가만). 아래는 모두 후속 작업 제안이다.

---

## P0 — 배포 차단

### P0-1. 상태 영속성 없음 + 단일 프로세스 가정 (프로덕션 서빙 불가)
- **위치**: `widu/pipeline.py`(`StreamProcessor._users`, `UserState`), `serving/api.py`(모듈 전역 `SP`, `app.run(...)`).
- **현상(검증)**: 모든 사용자 상태 — L1 개인 baseline(EWMA), L4 14일 추세 baseline, L5 알림 예산/활성 detection, self-check 대기 — 가 **프로세스 메모리 dict에만** 존재. DB·캐시·파일 영속화 코드 없음. 서버는 Flask 개발 서버(`app.run`)로 기동.
- **이유**: ① 재시작/배포마다 전 사용자 개인화·알림예산이 **0으로 리셋**(콜드스타트 재발 → 오탐↑). ② gunicorn/uwsgi 멀티워커로 띄우면 사용자 상태가 워커별로 갈라져 **판정 비결정**. ③ 개발 서버는 프로덕션 부적합(성능·보안).
- **제안**: (a) 사용자 상태를 외부 저장소(Redis/DB)로 빼거나 사용자→단일워커 스티키 라우팅. (b) baseline/예산은 주기적 영속화 + 기동 시 복원. (c) gunicorn 등 WSGI + 워커 수 결정 시 상태 공유 전략 함께. (d) 스레드 안전성 검토(현재 공유 dict에 락 없음).

### P0-2. API 인증·인가 전무
- **위치**: `serving/api.py` 전체(라우트에 인증 데코레이터 없음).
- **현상(검증)**: 모든 엔드포인트가 무인증 공개. `uid`만 알면 임의 사용자의 건강 신호 POST·상태 조회 가능.
- **이유**: 독거 고령자 **건강/위치(PII)** 데이터. 무인증은 보안·프라이버시(개인정보보호법) 위반 소지 + 위조 신호 주입 가능.
- **제안**: 단말/서버 간 토큰 인증(디바이스 키 또는 JWT) + `uid` 소유권 검증. 전송 구간 TLS. 레이트 리밋.

---

## P1 — 프로덕션 전 필수

### P1-1. `/healthz` 가 500을 반환(실제 버그)
- **위치**: `serving/api.py:41`.
- **현상(검증)**: `SP._fall_model.trained` 참조 — `StreamProcessor`에는 `_fall_model` 속성이 **없다**(`_forced_model`·`_models`만 존재, `grep`로 확인). 호출 시 `AttributeError` → **HTTP 500**. (테스트 `tests/test_api_smoke.py::test_healthz`가 이 버그를 잡아 현재 `xfail`로 표시.)
- **이유**: liveness/readiness probe가 이 엔드포인트에 의존하면 컨테이너가 영구 unhealthy.
- **제안**: 모델 적재 여부를 `SP._model_for("watch").trained`(또는 `SP._models`/`_forced_model` 기준)로 교정. 수정 후 위 테스트의 `@pytest.mark.xfail` 제거.

### P1-2. 입력 검증 부재 → 잘못된 요청에 500(400 아님)
- **위치**: `serving/api.py` 각 핸들러(`float(d["bpm"])`, `Accuracy(...)`, `RecordKind(...)` 등 직접 접근).
- **현상(검증)**: 필수 필드 누락 → `KeyError` → **500**. 잘못된 enum(`accuracy`/`kind`) → `ValueError` → **500**. (in-process 호출로 확인.)
- **이유**: 클라이언트가 4xx로 구분 못 함 → 재시도 폭주·디버깅 난이도↑. 표준 REST 계약 위반.
- **제안**: 스키마 검증 레이어(pydantic/marshmallow 또는 수동) 도입 → 누락·타입오류·잘못된 enum은 **400 + 에러 본문**. 전역 에러 핸들러로 500 노출 차단.

### P1-3. IMU `source`(watch/phone) 미수용 → 위치별 모델 미활용
- **위치**: `serving/api.py:52-58`(`imu` 핸들러), 대비 `widu/types.py:IMUSample.source`, `widu/pipeline.py:_model_for`/`_wear_source`.
- **현상(검증)**: 타입·파이프라인은 `source`로 워치(손목)/폰(허리)을 분리해 위치별 모델(wrist/waist)·착용기기 라우팅을 한다. 그러나 `/imu` 엔드포인트는 `IMUSample`을 **위치 인자만으로 생성**(source 미전달) → 항상 `source="watch"`. `source` 키를 보내도 무시됨(200).
- **이유**: 제품 핵심(낙상)이 항상 손목 모델만 사용 → 폰(허리, SisFall, 더 높은 LODO F1 0.90) 경로가 죽어 있음. 폰-단독 폴백·교차검증도 동작 불가.
- **제안**: `/imu`가 `source`(+선택 `accuracy`)를 수용하도록 확장. `IMUSample(..., source=d.get("source","watch"))`. 프론트와 신호원 표기 합의(§API_CONTRACTS §6).

### P1-4. 네이티브 낙상(애플/삼성) 라우트 미노출
- **위치**: `widu/pipeline.py:ingest_fall_event`(구현됨) ↔ `serving/api.py`(해당 라우트 없음).
- **현상(검증)**: 워치 OS 자체 낙상 이벤트를 수용하는 메서드는 있으나 HTTP 엔드포인트가 없어 외부에서 호출 불가.
- **이유**: README가 강조하는 "네이티브 위임" 융합이 실제로는 진입 경로 없음.
- **제안**: `POST /users/<uid>/native_fall {source, confidence?, ts?}` 추가해 `ingest_fall_event` 위임.

### P1-5. 의존성 버전 고정·락파일 부재(재현성)
- **위치**: `requirements.txt`(하한 `>=`만), `pyproject.toml`(상한·고정 없음). 락파일(`requirements.lock`/`poetry.lock`/`uv.lock`) 없음.
- **현상(검증)**: numpy/pandas/scipy/scikit-learn 등이 상한 없이 설치 → 향후 메이저 업데이트로 동작·모델 호환성 변동 위험. 특히 **scikit-learn 버전이 바뀌면 `*.joblib` 역직렬화 경고/실패** 가능.
- **이유**: "야간 무인 + 재현 가능" 운영에 비결정적. 모델은 학습 시 sklearn 버전에 민감.
- **제안**: 락파일 도입(또는 `==` 핀 + Dependabot). 모델 생성에 쓰인 sklearn 버전을 `models/`에 기록. CI에서 핀 설치.

### P1-6. 서버→클라이언트 알림 전달 경로 미구현
- **위치**: `serving/api.py`(푸시/웹소켓 없음). `escalation` 값(guardian_push/auto_call)은 **문자열로만** 반환.
- **현상(검증)**: 위급 판정 시 보호자에게 실제로 푸시를 보내는 코드가 없다. 응답 본문에 의도만 표기.
- **이유**: 제품 목적(가족 알림)의 마지막 1마일이 비어 있음.
- **제안**: FCM/APNs 연동 + 보호자 등록 모델. 프론트 폴링(`GET /status`)은 임시 수단.

---

## P2 — 정리 · 문서 · 일관성

### P2-1. 버전 문자열 불일치
- **위치**: `pyproject.toml` `version = "0.20.0"` vs `widu/__init__.py` `__version__ = "0.1.0"`.
- **제안**: 단일 출처로 통일(`importlib.metadata` 또는 한쪽 제거).

### P2-2. 레거시 lint 잔여(미사용 import 등)
- **위치**: `widu/gating.py`(`time`), `widu/pipeline.py`(`ActivityContext`), `widu/datasets/sisfall.py`(`List`), `widu/datasets/vitaldb.py`(`Optional`) 등 F401 4건. 스크립트에는 E702(세미콜론)·E402 다수(의도적 terse 스타일).
- **현상(검증)**: 추가한 `ruff.toml`은 실버그류(E9·F)만 게이트하고 위 4건은 per-file-ignore로 동결, `scripts/`는 제외. CI는 통과.
- **제안**: 코어의 미사용 import 4건 제거 후 `ruff.toml`의 해당 ignore 삭제. 스크립트 스타일은 선택.

### P2-3. Windows 콘솔(cp949) 인코딩 크래시
- **위치**: 이모지/한글을 stdout에 출력하는 스크립트(예: `scripts/golden_check.py`의 `✅`).
- **현상(검증)**: 기본 Windows 콘솔(cp949)에서 `UnicodeEncodeError`로 크래시. `PYTHONIOENCODING=utf-8`이면 정상. (Linux CI는 기본 utf-8이라 영향 없음 — CI에도 안전장치로 env 설정해 둠.)
- **제안**: 스크립트 진입 시 `sys.stdout.reconfigure(encoding="utf-8")` 또는 출력에서 비ASCII 제거. 문서에 Windows 실행 시 env 설정 안내.

### P2-4. README ↔ 코드 불일치(포트)
- **위치**: `README.md` §9/§10(":5000", "서빙 :5000") vs `serving/api.py`(실제 `port=5001`).
- **제안**: README를 5001로 정정(또는 포트를 환경변수화).

### P2-5. `RecordKind.SLEEP`/`STEPS` 무반응
- **위치**: `widu/types.py:RecordKind`(6종 정의) vs `widu/l4_trend.py`(RESTING_HR·SPO2·TEMP·HRV 4종만 처리).
- **현상(검증)**: SLEEP/STEPS는 입력 수용되나 탐지 로직 없음 → `{"status":"ok"}`만.
- **제안**: 의도된 미구현이면 문서/주석 명시, 아니면 처리 추가.

### P2-6. `escalation` 값 'self_check'가 설정 목록에 없음
- **위치**: `widu/l5_fusion.py:_escalate`(반환값 `"self_check"`) vs `widu/config.py:L5.ESCALATION`(4종에 self_check 없음).
- **현상(검증)**: 실제 반환되는 escalation 값이 ESCALATION 리스트에 미정의 — 소비측이 리스트로 검증하면 누락.
- **제안**: ESCALATION 리스트에 `self_check` 포함 또는 별도 분류 명시.

---

## 부록 — 이번 인수인계로 **추가**된 것 (이전엔 부재)

| 항목 | 추가 위치 | 비고 |
|---|---|---|
| pytest 스캐폴드 | `tests/test_l0_safety.py`, `test_l1_hr.py`, `test_l2_fall.py`, `test_api_smoke.py`, `conftest.py` | L0~L2 단위 + API 스모크. 27 통과·1 xfail(P1-1 버그) |
| CI | `.github/workflows/ci.yml` | ruff + 골든 회귀 + pytest (Python 3.9·3.11) |
| ruff 설정 | `ruff.toml` | 실버그류(E9·F)만, scripts 제외, 레거시 4건 동결 |
| 문서 | `docs/ARCHITECTURE.md`, `docs/API_CONTRACTS.md`, `docs/HANDOFF_ISSUES.md`, `docs/HANDOFF_SUMMARY.md` | 검증된 사실 기반 |

> 기존에도 `scripts/golden_check.py` + `tests/golden.json`(특성화 회귀)와 `scripts/reverify.py`(11라운드 자가검증)가 있었다. 위 스캐폴드는 이를 **대체가 아니라 보완**(표준 pytest/CI 진입로)한다.
