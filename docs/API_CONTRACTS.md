# WidU API 계약 — 프론트엔드 ↔ 백엔드 ↔ 모델 인터페이스

> **병렬 개발용 단일 기준 문서.** `serving/api.py`·`widu/types.py`·`widu/pipeline.py`를
> 읽고 **실제 동작을 in-process(Flask test_client)로 캡처해** 작성했다. 예시 JSON은 실제 응답이다.
> ⚠️ 표시는 현재 구현의 한계/주의(상세는 `docs/HANDOFF_ISSUES.md`).

---

## 0. 공통 사항

- **베이스 URL**: 기본 `http://0.0.0.0:5001` (`serving/api.py` 맨 아래 `app.run(..., port=5001)`).
  ⚠️ `README.md`는 5000으로 적혀 있으나 **실제 코드는 5001**.
- **인증**: 없음(현재 미구현). 모든 엔드포인트 공개.
- **요청 본문**: JSON. 서버는 `request.get_json(force=True)` 사용 → `Content-Type` 무관하게 JSON 파싱 시도.
  - 본문이 JSON이 아니면 **400**.
- **`uid`(사용자 식별자)**: URL 경로 파라미터. 임의 문자열. 첫 호출 시 사용자 상태 자동 생성(별도 등록 없음).
- **`ts`(타임스탬프)**: 모든 입력에서 **선택**. 절대 epoch 초(float). 생략 시 서버 수신시각(`time.time()`).
- **입력 검증 없음**(⚠️ P1): 필수 필드 누락 → `KeyError` → **HTTP 500**. 잘못된 enum 값(`accuracy`/`kind`) → `ValueError` → **HTTP 500**. (400이 아니다 — 클라이언트는 4xx를 기대하면 안 됨.)
- **단위**: 가속도 = g(중력 정규화), 자이로 = rad/s, SpO₂ = 0.0~1.0, 체온 = °C, HRV = ms, 거리 = m.

---

## 1. 핵심 응답 객체 — `Assessment`

대부분의 신호 입력과 `/status`가 반환하는 **융합 판단**. (`widu/types.py:Assessment.to_dict`)

| 필드 | 타입 | 설명 |
|---|---|---|
| `ts` | float | 평가 시각(epoch 초) |
| `level` | string(enum) | `NORMAL` \| `INFO` \| `CAUTION` \| `EMERGENCY` \| `NO_CONTACT` |
| `reason` | string | 보호자용 한국어 근거(예: `"[위급] 낙상 후 움직임이 없습니다"`) |
| `escalation` | string(enum) | `in_app` \| `watch_haptic` \| `guardian_push` \| `auto_call` \| `self_check` |
| `context` | string(enum) | `SLEEP` \| `REST` \| `LOW` \| `ACTIVE` \| `UNKNOWN` (추정 활동맥락) |
| `detections` | array | 기여한 계층별 판단(아래 `Detection`) |

### `Detection` (detections 배열 원소)
| 필드 | 타입 | 설명 |
|---|---|---|
| `layer` | string | `"L0"`~`"L4"` (네이티브/무응답은 `"L2"`/`"L5"`) |
| `level` | string(enum) | AlertLevel |
| `scenario` | string | 시나리오 코드(아래 §4 카탈로그) |
| `source` | string | `"watch"` \| `"phone"` \| `""`(심박·위치 등 신호원 무관) |
| `score` | float | 0~1 신뢰도(반올림 3자리) |
| `evidence` | object | 시나리오별 근거(키는 시나리오마다 다름) |

**프론트엔드 매핑**: 앱 3-상태 = `NORMAL`→안정 / `CAUTION`→주의 / `EMERGENCY`→위급.
`INFO`는 소프트 인사이트(인앱), `NO_CONTACT`는 미착용(경보 아님).

> **3-상태 외 값 처리 주의**: 프론트는 `INFO`·`NO_CONTACT`와, escalation의 `self_check`(워치 본인확인 UX)도 처리해야 한다.

---

## 2. 엔드포인트 — 신호 입력

### `POST /users/<uid>/hr` — 심박 입력
요청:
| 필드 | 타입 | 필수 | 기본 | 비고 |
|---|---|---|---|---|
| `bpm` | float | ✅ | — | 심박수. 생리범위 밖(<20 또는 >240)은 게이트에서 폐기(경보 아님) |
| `ts` | float | ✖ | 서버시각 | |
| `accuracy` | string | ✖ | `"UNKNOWN"` | `HIGH`\|`MEDIUM`\|`LOW`\|`NO_CONTACT`\|`UNRELIABLE`\|`UNKNOWN`. `NO_CONTACT`=미착용 |

응답: **`Assessment`** (항상 200, 융합 결과).
```json
{ "ts": 1700000000.0, "level": "NORMAL", "reason": "안정",
  "escalation": "in_app", "context": "UNKNOWN", "detections": [] }
```

### `POST /users/<uid>/imu` — 가속도/자이로 입력
요청:
| 필드 | 타입 | 필수 | 기본 | 비고 |
|---|---|---|---|---|
| `ax`,`ay`,`az` | float | ✅ | — | 가속도(g) |
| `gx`,`gy`,`gz` | float | ✖ | 0.0 | 자이로(rad/s) |
| `ts` | float | ✖ | 서버시각 | |

응답: 탐지 발생 시 **`Assessment`**, 아니면 **`{"status":"ok"}`** (둘 다 200).
```json
{ "status": "ok" }
```
EMERGENCY 발생 예시(낙상 후 무활동):
```json
{ "ts": 1700000010.92, "level": "EMERGENCY",
  "reason": "[위급] 낙상 후 움직임이 없습니다",
  "escalation": "auto_call", "context": "REST",
  "detections": [ { "layer": "L2", "level": "EMERGENCY",
    "scenario": "fall_long_lie", "source": "watch", "score": 0.53,
    "evidence": { "fall_proba": 0.33, "impact_g": 4.9, "impact_driven": false,
      "post_immobile_s": 8.0, "source": "watch" } } ] }
```
> ⚠️ **`source` 미지원(P1)**: 타입 `IMUSample`에는 `source`(watch/phone) 필드가 있으나
> **이 엔드포인트는 받지 않는다** — 모든 API IMU는 항상 `source="watch"`로 처리된다.
> (`source` 키를 보내도 무시되고 200.) 폰(허리) IMU를 구분해 위치별 모델(waist)을 태우려면
> 엔드포인트 확장이 필요하다. `accuracy` 필드도 동일하게 미수용.

### `POST /users/<uid>/location` — 위치 입력
요청:
| 필드 | 타입 | 필수 | 기본 |
|---|---|---|---|
| `lat`,`lon` | float | ✅ | — |
| `speed` | float | ✖ | null (m/s) |
| `ts` | float | ✖ | 서버시각 |

응답: 탐지 시 **`Assessment`**, 아니면 **`{"status":"ok"}`**. (안전구역 미설정 시 항상 ok)

### `POST /users/<uid>/record` — 기록형 지표 입력
요청:
| 필드 | 타입 | 필수 | 비고 |
|---|---|---|---|
| `kind` | string | ✅ | `SPO2`\|`TEMP`\|`HRV`\|`RESTING_HR`\|`SLEEP`\|`STEPS`. ⚠️ 현재 **탐지 로직이 있는 건 앞 4종**, `SLEEP`/`STEPS`는 수용되나 무반응(`{"status":"ok"}`) |
| `value` | float | ✅ | SpO₂=0~1, 체온=°C, HRV=ms, RESTING_HR=bpm |
| `ts` | float | ✖ | |

응답: 탐지(INFO 조기경보) 시 **`Assessment`**, 아니면 **`{"status":"ok"}`**.

---

## 3. 엔드포인트 — 설정 · 조회 · 능동학습 · 헬스

### `POST /users/<uid>/safezones` — 안전구역 설정
요청: `{ "zones": [[lat, lon, radius_m], ...] }` (`zones` 필수, 각 원소 3-튜플)
응답: `{ "status": "ok", "count": <int> }`

### `GET /users/<uid>/status` — 현재 융합 상태 조회
응답: **`Assessment`** (마지막 `ts` 기준 재평가). 신호 한 번도 없으면 `level=NORMAL`.

### `POST /users/<uid>/respond_ok` — self-check "괜찮아요"
본문: `{ "ts"?: float }` (선택, 본문 생략 가능). self-check 격상 취소 + 능동학습 라벨=`false_alarm`.
응답: **`Assessment`**.

### `POST /users/<uid>/confirm_incident` — 사후 확인(가족/사용자)
요청:
| 필드 | 타입 | 필수 | 기본 |
|---|---|---|---|
| `is_fall` | bool | ✅ | — |
| `by` | string | ✖ | `"guardian"` |

응답: `{ "status": "ok", "sample_id": <str|null>, "labeled": <bool> }`
(대기 중 라벨 이벤트가 없거나 수집 비활성이면 `sample_id=null, labeled=false`.)
```json
{ "status": "ok", "sample_id": null, "labeled": false }
```

### `GET /collector/stats` — 능동학습 수집 통계
응답:
```json
{ "enabled": false, "pending": 0, "collected": 0,
  "fall": 0, "false_alarm": 0, "by": {} }
```
> 수집은 환경변수 `WIDU_COLLECT=1` + 사용자 동의 시에만 활성(기본 off).

### `GET /healthz` — 헬스체크
의도된 응답: `{ "ok": true, "service": "widu", "fall_model": <bool> }`
> ⚠️ **현재 깨져 있음(P1-1)**: 코드가 존재하지 않는 `SP._fall_model`을 참조해 **HTTP 500**을 반환한다.
> 배포 전 수정 필요(liveness/readiness probe가 이 엔드포인트에 의존하면 안 됨). 상세 `HANDOFF_ISSUES.md`.

---

## 4. 시나리오 코드 카탈로그 (`scenario` 값)

`detections[].scenario`로 내려오는 전체 목록. 한국어 문구는 `l5_fusion._SCENARIO_KO`.

| 계층 | scenario | 기본 level | 의미 |
|---|---|---|---|
| L0 | `flatline_arrest` | EMERGENCY | 무박동(실신·정지 의심) |
| L0 | `bradycardia` | EMERGENCY | 중증 서맥 |
| L0 | `tachycardia` | EMERGENCY | 중증 빈맥 |
| L0 | `resting_tachycardia` | EMERGENCY | 안정 상태 빈맥 |
| L1 | `hr_high` / `hr_low` | CAUTION/EMERGENCY | 개인 baseline 대비 고/저심박 |
| L2 | `fall_long_lie` | EMERGENCY | 낙상 후 무활동 |
| L2 | `fall_recovered` | CAUTION | 낙상 충격(회복) |
| L2 | `fall_suspected` | CAUTION | 낙상 의심(→ self-check) |
| L2 | `fall_confirmed` | EMERGENCY | 네이티브 낙상 수용(현재 라우트 미노출, §5) |
| L3 | `immobility_12h` | EMERGENCY→CAUTION | 12h 무활동(단독 시 격하) |
| L3 | `fall_unrecovered` | EMERGENCY | 넘어진 뒤 미회복(3분) |
| L3 | `wandering_night` | CAUTION | 야간 배회 |
| L3 | `safezone_exit` | INFO | 안전구역 이탈(주간) |
| L4 | `resting_hr_uptrend` | INFO | 안정심박 상승(감염 조기경보) |
| L4 | `spo2_low_trend` | INFO | SpO₂ 저하 추세 |
| L4 | `temp_uptrend` | INFO | 체온 상승 추세 |
| L5 | `no_response_fall` | EMERGENCY | 낙상 의심 후 45초 무응답 |

---

## 5. 모델 인터페이스 계약 (backend ↔ model)

- **낙상 모델**: `models/fall_rf.joblib`(기본) + `fall_rf_wrist.joblib`(워치) + `fall_rf_waist.joblib`(폰).
  - 입력: `extract_features(window(N,6), fs=50)` → **23차원 벡터**(순서 = `widu/l2_fall.py:FALL_FEATURES`, 변경 금지 계약).
  - 출력: `predict_proba(...)[0,1]` = 낙상 확률. 임계: watch 0.30 / phone 0.40.
  - 모델 파일 없으면 휴리스틱 폴백(결정적). `FallModel.trained`로 적재 여부 확인.
- **위치별 라우팅**은 IMU `source`에 의존하나, 현재 **API가 source를 받지 않아 항상 wrist 경로**(§2 ⚠️).
- **네이티브 낙상**(애플 `CMFallDetectionManager`/삼성 `FALL_DETECTED`): `StreamProcessor.ingest_fall_event()`가 구현돼 있으나 **Flask 라우트로 노출돼 있지 않다**(P1) — 워치 컴패니언 연동 전 라우트 추가 필요.

---

## 6. 프론트↔백엔드 통합 체크리스트(병렬 작업용)

1. **상태 폴링 vs 푸시**: 현재는 신호 POST의 응답으로 Assessment를 받거나 `GET /status`로 폴링. 서버→앱 푸시(웹소켓/FCM)는 미구현 → 보호자 알림 전달 경로는 별도 설계 필요.
2. **에러 계약**: 현재 잘못된 입력이 500을 낸다. 프론트는 5xx 재시도 로직에 주의(검증 추가 전까지). 백엔드 입력검증(→400) 도입이 P1.
3. **source 구분**: 폰/워치 IMU를 나눠 보내려면 `/imu`에 `source` 수용 추가 합의 필요.
4. **타임스탬프**: 가능하면 클라이언트가 `ts`(절대 epoch 초)를 보내 단말-서버 시계차를 흡수.
5. **알림 예산**: 서버가 하루 6건으로 guardian_push를 제한(`ALERT_BUDGET_PER_DAY`). 초과 시 `watch_haptic`으로 강등됨 — UX에서 인지 필요.
