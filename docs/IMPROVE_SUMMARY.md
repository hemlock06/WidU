# WidU improve — 야간 무인 개선 요약 (2026-06-28)

> 브랜치: `improve` (← `handoff-prep` 분기). main·handoff-prep 미수정.
> 범위: `docs/HANDOFF_ISSUES.md` 의 P0/P1/P2 중 **안전·독립검증 가능 + 허용 카테고리**
> (버그수정+테스트 / 입력·에러 강건화 / 핵심경로 단정 테스트 / 의존성 버전 핀 / 재현성)만 구현.
> 인증·인가 / 상태 영속성·DB / 푸시 전달 등 **설계결정 필요한 건 구현하지 않고 제안만**
> (`docs/IMPROVE_PROPOSALS.md`).

---

## 1. 한 일 (구현 + 검증됨)

| ID | 항목 | 변경 | 검증 |
|---|---|---|---|
| **P1-1** | `/healthz` 500 버그 | `SP._fall_model.trained`(존재X) → `SP._model_for("watch").trained` 로 교정. `serving/api.py` | `tests/test_api_smoke.py::test_healthz` xfail 제거 → 200·bool 단정 통과 |
| **P1-2** | 입력검증 → 400 / 내부오류 → 500 | **외과적 버전**(WidU=운영서버 대상, 커밋 `260573b`): 핸들러 입구에서 입력만 명시검증(`_require`/`_num`/`_enum`/`_ts`) → 잘못된 입력만 400. `errorhandler(HTTPException)`=원래 상태코드 유지, `errorhandler(Exception)`=500. **내부 코드 버그가 400으로 위장되지 않고 500으로 노출**(운영 모니터링). `serving/api.py` | 신규 5 테스트(입력오류 4건→400 + 내부오류→500) |
| **P1-3** | `/imu` `source` 미수용 | `/imu` 가 `source`(watch/phone) 를 `IMUSample` 에 전달 → 위치별 모델 라우팅 활성. 미전달 시 기존 동작(`watch`) 보존. (accuracy 는 파이프라인 미소비 → 의도적 미수용) | 신규 2 테스트: phone 전달 시 `SP._users[uid].l2` 에 `phone` 탐지기 생성 / 기본은 `watch` |
| **P1-4** | 네이티브 낙상 라우트 부재 | `POST /users/<uid>/native_fall {source?,confidence?,ts?}` 추가 → 기존 `ingest_fall_event` 위임. `serving/api.py` | 신규 1 테스트: 200 + level EMERGENCY + Assessment 키 |
| **P1-5** | 의존성 핀·재현성 | `requirements.lock`(정확 버전 핀, ASCII 전용) + `models/VERSIONS.md`(모델 joblib 호환 sklearn 1.9.0 기록). `requirements.txt`(범위)는 **미변경**(3.9 CI 잡 보존). | lock `pip install --dry-run` 해결(exit 0) / 모델 로드 InconsistentVersionWarning 없음 |
| **P2-1** | 버전 문자열 불일치 | `widu/__init__.py` `__version__` = importlib.metadata(설치본) **또는** 폴백 `"0.20.0"` → pyproject(0.20.0)와 단일화(과거 0.1.0). | 신규 2 테스트: 비어있지 않은 str / pyproject 버전과 일치 |
| **P2-2** | 레거시 미사용 import | `gating.py:time`, `pipeline.py:ActivityContext`, `sisfall.py:List`, `vitaldb.py:Optional` 4건 제거 + `ruff.toml` per-file-ignores(F401 동결) 4건 삭제. | `ruff check .` clean (이제 widu/ 전체 F401 적용) |
| **P2-3** | Windows cp949 크래시 | `scripts/golden_check.py` 진입부 `sys.stdout.reconfigure(encoding="utf-8")` 가드(불가 환경은 조용히 무시). | 직접 재현: 강제 cp949(`PYTHONLEGACYWINDOWSSTDIO=1`)에서 raw print 는 crash(exit1), 가드된 스크립트는 정상(exit0) |
| **P2-4** | README 포트 불일치 | `README.md` `:5000` → `:5001`(실제 `app.run(port=5001)`). | grep 확인(잔여 5000 없음) |
| **P2-6** | `self_check` 가 ESCALATION 목록에 없음 | `config.py:L5.ESCALATION` 에 `"self_check"` 추가(목록은 미사용 화이트리스트라 동작 불변). | 신규 2 테스트: `self_check` 포함 / `_escalate` 의 모든 return 리터럴(AST 정적추출) ⊆ ESCALATION |

## 2. 테스트 결과 (improve 브랜치, Python 3.11.15 · Windows)

- `ruff check .` → **All checks passed**
- `python scripts/golden_check.py check` → **11/11 케이스 일치(동작 불변)**
- `pytest tests/` → **40 passed, 0 xfailed** (베이스라인 27 passed·1 xfailed → healthz xfail 해소 + 신규 12 테스트; P1-2 외과적 전환 후 내부오류→500 테스트 포함)
- `pip install --dry-run -r requirements.lock` → **해결(exit 0)**

> 변경 잔류 기준 충족: 빌드·기존 테스트·골든 회귀 전부 통과(깨진 것 없음).

## 3. 독립검증 (무인+쓰기 → '다른 눈')

1. **기존 테스트 스위트 + 골든 회귀** 통과 = 동작 불변 보증.
2. **새 컨텍스트 적대적 diff 리뷰 1패스**(서브에이전트, 버그·회귀·요구오해만) 수행.
   - 판정: **SAFE TO KEEP** (기능 버그 0, 금지 카테고리 침범 0).
   - 지적 2건(우려, 버그 아님) 처리:
     - (B) `/imu` accuracy(int) vs HR accuracy(enum) 불일치 → **수정**: IMUSample.accuracy 가 파이프라인에서 미소비임을 확인하고 accuracy 수용을 제거, `source` 만 전달(불일치 제거).
     - (A) 전역 errorhandler 가 내부 500급 오류를 400으로 가릴 수 있음(관측성 저하) → **외과적 버전으로 교체**(WidU 는 운영서버 대상이라 결정, 커밋 `260573b`): 입력만 400, 내부 버그는 500 으로 노출. 관측성 트레이드오프 해소.

## 4. 미검증 / 한계 (정직)

- **CI Python 3.9 잡**: 본 작업 환경(3.11)에서만 검증. `requirements.lock` 의 numpy 2.4 / pandas 3.0 / sklearn 1.9 는 3.9 미지원이므로 lock 은 3.9 에 쓰지 않음(범위 `requirements.txt` 로 설치). 3.9 호환 핀은 미검증 → 제안만.
- **모델 *학습* 시 정확한 sklearn 버전**: 인수인계 메타에 없음 → `VERSIONS.md` 는 *로드 호환이 검증된* 1.9.0 만 기록(학습 버전은 추측하지 않음).
- **전역 errorhandler(A)**: ~~관측성 트레이드오프 존재~~ → **해소됨**(외과적 버전으로 교체, 입력 400 / 내부 500 분리. 위 3-(A)).

## 5. 미구현 — 제안만 (`docs/IMPROVE_PROPOSALS.md`)

P0-1(상태 영속성), P0-2(인증·인가), P1-6(푸시 전달), P2-5(SLEEP/STEPS 무반응 처리 결정), + 3.9 호환 핀 전략. 설계결정·독립검증 곤란으로 코드 미잔류.
> 참고: P1-2 경계검증(외과적) 대안은 *제안*이 아니라 **구현 완료**됨(WidU=운영서버 대상, 위 §1·§3). 커밋 `260573b`.
