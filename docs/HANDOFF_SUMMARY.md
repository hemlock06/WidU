# WidU 인수인계 요약 (HANDOFF_SUMMARY)

> 브랜치: **`handoff-prep`** (master 미수정·미푸시). 작업일: 2026-06-28.
> 원칙: **기존 소스 로직 무수정 — 추가만**. 코드를 읽고 **검증된 사실만** 문서화.

---

## 1. 한 일

### 문서 (`docs/`)
- **`ARCHITECTURE.md`** — 5계층(게이팅·L0~L5)+융합 구조, 데이터 계약, 모듈 맵, `StreamProcessor` 진입점, 계층별 검증된 동작·임계, 낙상 데이터 흐름.
- **`API_CONTRACTS.md`** — Flask 엔드포인트 11종의 요청/응답 스키마(필드·타입·필수·기본·단위) + **실제 캡처한 예시 JSON**(정상/EMERGENCY) + 시나리오 코드 카탈로그 + frontend↔backend↔model 계약 + 통합 체크리스트.
- **`HANDOFF_ISSUES.md`** — P0/P1/P2 actionable 이슈(위치·현상·이유·제안). 코드 검증으로 발견한 실버그 포함.
- **`HANDOFF_SUMMARY.md`** — 본 문서.

### 테스트 스캐폴드 (`tests/`, 추가만)
- `conftest.py` — 레포 루트 sys.path 부트스트랩.
- `test_l0_safety.py` — L0 서맥/빈맥/무박동/안정빈맥/지속성/맥락게이팅.
- `test_l1_hr.py` — L1 rest_only 게이팅·지속성·콜드스타트 후 발화.
- `test_l2_fall.py` — 특징 계약(23차원)·결정성·휴리스틱 폴백·하드충격→무활동 캐스케이드·위치별 임계.
- `test_api_smoke.py` — 11 엔드포인트 스모크(상태코드·필수 키). `/healthz`는 버그로 `xfail`.
- **결과: 27 passed, 1 xfailed** (Python 3.11, `PYTHONIOENCODING=utf-8`).

### CI (`.github/workflows/ci.yml`, 추가만)
- 트리거: push(master·handoff-prep)·PR·수동. 매트릭스 Python **3.9·3.11**.
- 단계: deps 설치 → **ruff**(실버그류 린트) → **골든 회귀**(`golden_check.py check`) → **pytest**.

### 린트 설정 (`ruff.toml`, 추가만)
- 실버그류(`E9`+`F`)만 게이트. `scripts/`(의도적 terse 스타일) 제외. 레거시 미사용 import 4건 동결.
- 로컬 검증: `ruff check .` → **All checks passed (exit 0)**.

---

## 2. 검증 방법 (실제로 돌려서 확인)

| 검증 | 명령 | 결과 |
|---|---|---|
| 기존 동작 불변 | `python scripts/golden_check.py check` | ✅ 골든 11/11 일치 |
| 신규 테스트 | `python -m pytest tests/ -q` | ✅ 27 passed, 1 xfailed |
| 린트 게이트 | `python -m ruff check .` | ✅ All checks passed |
| API 응답 계약 | Flask `test_client` in-process 캡처 | ✅ 예시 JSON 문서화 |

> 검증을 위해 런타임 의존성과 `pytest`·`ruff`를 현재 환경에 설치했다(레포 변경 아님).

### 검증 중 발견한 실버그·불일치(추측 아님)
- **`/healthz` 500**: `serving/api.py:41`이 존재하지 않는 `SP._fall_model` 참조(P1-1).
- **입력검증 부재**: 필수 필드 누락/잘못된 enum → 500(400 아님)(P1-2).
- **IMU `source` 미수용**: 항상 watch 처리 → 폰(허리) 모델 미사용(P1-3).
- **네이티브 낙상 라우트 미노출**(P1-4).
- **버전 불일치**: pyproject 0.20.0 vs `__init__` 0.1.0(P2-1). **README 포트** 5000 vs 실제 5001(P2-4).

---

## 3. 미완 / 손대지 않은 것

- **기존 소스 로직 일절 미수정**(원칙). 위 P0~P2 이슈는 **수정하지 않고 기록만** 했다 — 후속 작업자가 결정·적용.
- **`/healthz` 버그 미수정**: 테스트를 `xfail`로 표시해 가시화만. 수정 시 마커 제거 필요(P1-1).
- **테스트 범위**: L0~L2 + API 스모크만(보수적, 확실한 것만). L3(지오펜스·무활동)·L4(CUSUM)·L5(융합 교차검증) 단위 테스트는 미작성 — 시간/타이밍 의존이 커 "확실한 것만" 원칙상 보류. 단 L5 핵심 융합은 기존 `golden_check.py`가 일부 커버.
- **CI 미실행 확인**: 워크플로 YAML은 추가했으나 GitHub Actions 상에서의 실제 실행은 push 후에야 검증 가능(푸시 금지라 로컬에서 각 단계만 동등 검증).
- **프로덕션 서빙·인증·알림 전달**: 미구현(P0-1/P0-2/P1-6). 설계 필요.

---

## 4. 다음 단계 (권장 순서)

1. **`handoff-prep` 리뷰 → master 병합**(문서·테스트·CI는 무해한 추가물).
2. **P1-1 `/healthz` 수정**(1줄) + `xfail` 제거 — CI 그린 확인용 빠른 승리.
3. **P1-2 입력검증**(400 응답) + 전역 에러 핸들러.
4. **P0-2 인증** / **P0-1 상태 영속성·서빙**(프로덕션 설계) — 백엔드 핵심.
5. **P1-3 IMU source 수용** — 프론트와 신호원 표기 합의 후(API_CONTRACTS §6 참조).
6. **P1-5 의존성 핀·락파일** — 모델 호환성 안정화.
7. L3~L5 테스트 확충, P1-6 알림 전달(FCM/APNs).

---

## 5. 빠른 시작 (새 개발자)

```bash
pip install -r requirements.txt
pip install pytest ruff                 # 개발 도구

# 검증
python scripts/golden_check.py check    # 동작 불변(Windows는 set PYTHONIOENCODING=utf-8)
pytest tests/ -v                        # 단위 + 스모크
ruff check .                            # 린트

# 실행
python serving/api.py                   # Flask :5001  (README의 5000은 오기)
```

문서 읽는 순서: **ARCHITECTURE → API_CONTRACTS → HANDOFF_ISSUES**.
설계 *근거*(왜 이렇게 만들었나)는 `README.md` + `docs/WidU_해설문서.docx`(D1~D38 의사결정 로그).
