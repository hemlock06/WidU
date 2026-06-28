# WidU 아키텍처 — 5계층 위급탐지 파이프라인

> 인수인계용 구조 문서. **실제 코드(`widu/`, `serving/`)를 읽고 검증한 사실만** 기록한다.
> 코드 라인 참조는 작성 시점(브랜치 `handoff-prep`) 기준. 설계 *근거*는 `README.md`·`docs/WidU_해설문서.docx`(D1~D38) 참조.

---

## 0. 한눈에

스마트워치·폰 센서(심박 1Hz, 가속도/자이로 50~200Hz, 위치, 기록형 지표)를 받아
**계층별로 가벼운→무거운 판단**을 쌓고, **L5에서 융합**해 3-상태(안정/주의/위급)와
에스컬레이션(in_app→watch_haptic→guardian_push→auto_call)을 산출한다.

```
                          ┌─────────────────────────────────────────────┐
   워치/폰/서버  ──HTTP──▶ │  serving/api.py (Flask)                      │
                          │     └─ StreamProcessor (widu/pipeline.py)    │  ← 진입점
                          └─────────────────────────────────────────────┘
                                            │  사용자별 UserState 라우팅
        ┌──────────────┬──────────────┬─────┴────────┬──────────────┬──────────────┐
        ▼              ▼              ▼              ▼              ▼              ▼
   gating          L0 안전룰      L1 개인심박     L2 낙상        L3 행동·위치    L4 추세
   (품질·맥락)     (하드 임상)    (맥락 z·지속)  (충격→캐스케이드) (지오펜스·무활동) (CUSUM 조기경보)
        │              │              │              │              │              │
        └──────────────┴──────────────┴──────┬───────┴──────────────┴──────────────┘
                                              ▼
                                   L5 융합 (widu/l5_fusion.py)
                                   교차검증·격상/격하·알림예산·self-check
                                              ▼
                                   Assessment (3-상태 + 에스컬레이션 + 근거)
```

---

## 1. 데이터 계약 (`widu/types.py`)

모든 계층이 공유하는 입출력 타입. 타임스탬프는 **절대 epoch 초(float)** 로 정규화.

### 입력 샘플
| 타입 | 필드 | 단위/비고 |
|---|---|---|
| `HRSample` | `ts, bpm, accuracy=Accuracy.UNKNOWN` | bpm float, 1Hz |
| `IMUSample` | `ts, ax, ay, az, gx=0, gy=0, gz=0, accuracy=3, source="watch"` | acc=g, gyro=rad/s. `source ∈ {"watch","phone"}` |
| `LocSample` | `ts, lat, lon, speed=None` | speed m/s(옵션) |
| `RecordSample` | `ts, kind: RecordKind, value` | 기록형 지표 |

### 열거형
- `Accuracy`: `HIGH, MEDIUM, LOW, NO_CONTACT, UNRELIABLE, UNKNOWN`
  - `is_trustworthy` = HIGH/MEDIUM
- `ActivityContext`: `SLEEP, REST, LOW, ACTIVE, UNKNOWN`
- `AlertLevel`: `NORMAL, INFO, CAUTION, EMERGENCY, NO_CONTACT` (`rank`: NO_CONTACT=-1, NORMAL=0, INFO=1, CAUTION=2, EMERGENCY=3)
- `RecordKind`: `SPO2, TEMP, HRV, SLEEP, STEPS, RESTING_HR`
  - ⚠️ L4가 실제 처리하는 kind는 **RESTING_HR·SPO2·TEMP·HRV** 4종. `SLEEP·STEPS`는 입력 가능하나 현재 탐지 로직 없음(→ None).

### 출력
- `Detection(layer, level, scenario, score, ts, evidence, source)` — 한 계층의 단일 판단.
- `Assessment(ts, level, reason_ko, detections, escalation, context)` — L5 융합 후 최종.
  - `to_dict()` → `{ts, level, reason, escalation, context, detections[]}` (API 응답 본체)

---

## 2. 진입점 — `StreamProcessor` (`widu/pipeline.py`)

사용자별 상태(`UserState`)를 보유하고, 들어온 신호를 해당 계층으로 라우팅한 뒤 L5 융합 결과를 반환한다.

### UserState 구성 (사용자 1인당)
`activity`(ActivityEstimator) · `l0`(L0Safety) · `l1`(PersonalHRModel) ·
`l2`(Dict[source→FallDetector]) · `l3`(BehaviorMonitor) · `l4`(TrendMonitor) ·
`fusion`(FusionEngine) + 상태값(`last_ts, no_contact, last_seen, pending_check, imu_buffer, pending_event_id`).

### 입력 메서드 (라우팅)
| 메서드 | 처리 | 반환 |
|---|---|---|
| `ingest_hr(user, HRSample)` | quality_gate → 활동맥락·아티팩트 산출 → L0+L1 → fusion | `Assessment` (항상) |
| `ingest_imu(user, IMUSample)` | source별 FallDetector(L2) → 충격 시 L3 미회복 무장 → 착용기기면 활동맥락·L3 무활동 → self-check 무장/타임아웃 | `Optional[Assessment]` (탐지/타임아웃 시만) |
| `ingest_location(user, LocSample)` | L3 지오펜스·배회 | `Optional[Assessment]` |
| `ingest_record(user, RecordSample)` | L4 추세 | `Optional[Assessment]` |
| `ingest_fall_event(user, ts, source, confidence)` | 네이티브 낙상(애플/삼성) 수용 → fall_confirmed + L3 미회복 무장 | `Assessment` |
| `respond_ok(user, ts)` | self-check "괜찮아요" → 대기 해제 + 능동학습 라벨=false_alarm | `Assessment` |
| `confirm_incident(user, is_fall, by)` | 사후 확인 → 능동학습 라벨 적재 | `Optional[str]` (sample_id) |
| `set_safe_zones / status` | 안전구역 설정 / 현재 융합상태 조회 | — / `Assessment` |

### 착용기기 라우팅 (`_wear_source`)
활동맥락·무활동 판정의 기준 기기 선택: 최근 `WEAR_GAP_SEC=60s` 내 watch 신호 있으면 **watch**,
없으면 phone(폰-단독 폴백), 둘 다 없으면 기본 `WEAR_SOURCE="watch"`.
낙상(L2)은 기기별 위치가 달라 **source별 독립 FallDetector**로 처리.

### 모델 로딩 (`_model_for`)
source별 위치 모델을 lazy-load: `L2.MODEL_BY_SOURCE`(watch→wrist, phone→waist).
해당 위치 모델이 없으면 기본 `fall_rf.joblib`로 폴백, 그것도 없으면 휴리스틱.

---

## 3. 게이팅 (`widu/gating.py`) — L0 앞단

1. **`quality_gate(hr)` → (use_sample, is_no_contact)**
   - `NO_CONTACT` → (False, True): 미착용 = 경보 아님.
   - `UNRELIABLE` 또는 bpm ∉ [20, 240] → (False, False): 계산에서 제외.
2. **`ActivityEstimator`** — 가속도 동적성분(SMV-1g)의 윈도우 평균(SMA)으로 맥락 추정.
   `SMA_REST=0.04 / SMA_LOW=0.20 / SMA_ACTIVE=0.6`. REST 구간이 23~6시면 SLEEP로.
3. **`is_motion_artifact_risk()`** — SMA ≥ SMA_ACTIVE면 HR 스파이크를 아티팩트로 감점(L1에 전달).

---

## 4. 계층별 요약 (검증된 동작)

### L0 — 결정적 안전룰 (`widu/l0_safety.py`, 임계 `config.L0`)
임계+지속성(`SUSTAIN_SEC=30s`)으로 명백한 임상 이벤트 발화. 모두 `EMERGENCY`.
| scenario | 조건 |
|---|---|
| `flatline_arrest` | bpm < 25 (`HR_FLATLINE`) 30s |
| `bradycardia` | bpm < 40 (`HR_BRADY_HARD`) 30s |
| `tachycardia` | bpm > 150 (`HR_TACHY_HARD`) 30s |
| `resting_tachycardia` | REST/SLEEP 맥락 & bpm > 130 (`HR_TACHY_REST`) 30s |
검사 우선순위 = 위 표 순서(flatline이 brady보다 먼저). 단발 샘플은 발화 안 함.

### L1 — 개인화 심박 (`widu/l1_hr.py`, `config.L1`)
(사용자×맥락)별 EWMA 평균/표준편차 → 맥락조건부 z-score.
- **rest_only=True**: REST/SLEEP 외 맥락은 탐지 안 함(활동 중 심박 무시 → 오탐 제거).
- z ≥ `Z_CAUTION=3.0` → CAUTION, z ≥ `Z_EMERGENCY=4.5` → EMERGENCY(단 콜드스타트 `MIN_SAMPLES=60` 전에는 CAUTION까지만).
- **지속성 `SUSTAIN_SEC=180s`(3분)** 유지 시에만 발화. 정상 z(`<Z_CAUTION`) 표본만 baseline 갱신(오염 방지).
- scenario: `hr_high` / `hr_low`. 콜드스타트 prior는 `L1.PRIOR`(맥락별 mean/std).

### L2 — 낙상 (`widu/l2_fall.py`, `config.L2`)
2단계 캐스케이드 + 위치별 RandomForest + 파형-무관 안전망.
- **특징 계약**: `FALL_FEATURES` = **23개**(base 14 + extra 9). 학습/추론 공유(`extract_features`). extra는 반드시 끝에 추가(휴리스틱 폴백이 feat[0,1,2,12,13] 사용).
- **충격 트리거** `IMPACT_G=1.8g` → 사후 윈도우 수집 → 분류(`WIN_SEC=2.0`, `FS=50`, pre_frac=0.75).
- **위치별 임계** `FALL_PROBA_TH_BY_SOURCE`: watch 0.30 / phone 0.40(없으면 기본 0.40).
- **파형-무관 안전망**: `IMPACT_HARD_G=3.0` 이상 충격은 분류기 proba와 무관하게 후보 → 사후 무활동(`POST_IMMOBILE_SEC=8.0`, std<0.06) 동반 시 `fall_long_lie`(EMERGENCY).
- **회색지대** `FALL_PROBA_SOFT=0.15` ≤ proba < th → `fall_suspected`(CAUTION) → self-check 유도.
- scenario: `fall_long_lie`(EMERGENCY) · `fall_recovered`(CAUTION) · `fall_suspected`(CAUTION).

### L3 — 행동·위치 (`widu/l3_behavior.py`, `config.L3`)
- **무활동**: 활동(LOW/ACTIVE) 없이 `IMMOBILE_HARD_SEC=12h` → `immobility_12h`(EMERGENCY, L5에서 단독 시 CAUTION 격하). 데이터 공백 >30분이면 시계 리셋(공백을 무활동으로 오인 금지).
- **넘어진 뒤 미회복**: L2 충격(`POST_FALL_ARM_G=2.5` 이상) 무장 후 `POST_FALL_WATCH_SEC=180s` 무활동 → `fall_unrecovered`(EMERGENCY). (충격 직후 `POST_FALL_GRACE_SEC=10s`는 회복 오인 방지.)
- **지오펜스**: 안전구역 밖 `SAFEZONE_EXIT_M=150m` 초과 → 야간(23~5시)이면 `wandering_night`(CAUTION), 주간이면 `safezone_exit`(INFO). haversine 거리.

### L4 — 느린 추세 (`widu/l4_trend.py`, `config.L4`)
일일 베이스라인(`BASELINE_DAYS=14`) + 단방향 CUSUM(`K=0.5, H=5.0`). 모두 `INFO`(조기경보, 응급 아님).
| scenario | 조건 |
|---|---|
| `resting_hr_uptrend` | RESTING_HR가 baseline+8bpm & cusum>H (감염 조기경보) |
| `spo2_low_trend` | SPO2 < 0.94 |
| `temp_uptrend` | TEMP가 baseline+0.7°C & cusum>H |

### L5 — 융합·에스컬레이션 (`widu/l5_fusion.py`, `config.L5`)
`FusionEngine`(사용자 1인 상태기계). 활성 Detection을 TTL 동안 보관하며 교차검증.
- **TTL**(초): L0=90, L1=90, L2=600, L3=1800, L4=86400. 신호원(source)별 별도 보관 → 교차검증.
- **최종 레벨** = 활성 detection 중 (rank, score) 최대.
- **교차검증 규칙**:
  - 운동(ACTIVE) 맥락의 단독 `hr_high` EMERGENCY → CAUTION 격하.
  - `hr_high/low` + 무활동(`immobility_12h`/`fall_long_lie`) → EMERGENCY 격상.
  - 낙상 워치+폰 2개 source 동시 → 교차확인 보강(억제 안 함).
  - 단독 `immobility_12h` EMERGENCY → CAUTION 격하(충격/이상심박 미동반 시).
- **에스컬레이션**(`_escalate`): `fall_suspected` CAUTION → `self_check`(예산 미소모) / EMERGENCY → critical(flatline·fall_long_lie·brady·tachy)이면 `auto_call`, 아니면 `guardian_push` / CAUTION → 예산 내면 `guardian_push`, 초과면 `watch_haptic` / INFO → `in_app`.
- **알림 예산** `ALERT_BUDGET_PER_DAY=6`(일/사용자). `SELF_CHECK_SEC=45s` 무응답 → `no_response_fall` 격상(파이프라인 처리).
- ⚠️ 코드상 에스컬레이션 값 `self_check`는 `config.L5.ESCALATION` 리스트에는 없음(리스트는 in_app/watch_haptic/guardian_push/auto_call 4종).

---

## 5. 능동학습 데이터 엔진 (`widu/datalog.py`)

`ActiveLearningCollector`(동의 시에만 `enabled`). 라벨 가치 있는 이벤트(`_CAPTURE_SCENARIOS`)
발생 시 직전 IMU 윈도우(링버퍼 500=10초@50Hz) 스냅샷 → respond_ok/confirm_incident 응답이 곧 라벨.
- 저장: `data/active_learning/index.jsonl`(메타) + `windows/<sample_id>.npy`((N,6) float32).
- 라벨: `fall` / `false_alarm`. 프라이버시: 신호+라벨+최소 메타만(원좌표·식별자 없음).

---

## 6. 모듈 맵

```
widu/
  types.py        공통 데이터 계약(샘플·열거형·Detection·Assessment)
  config.py       전역 임계·경로(ROOT 상대, 환경독립). L0~L5·Activity 클래스
  gating.py       품질 게이트 + 활동맥락 추정 + 아티팩트
  l0_safety.py    L0 결정적 안전룰
  l1_hr.py        L1 개인화 심박(EWMA·z·지속성)
  l2_fall.py      L2 낙상(특징추출·FallModel·FallDetector 캐스케이드)
  l3_behavior.py  L3 지오펜스·무활동·미회복·배회
  l4_trend.py     L4 CUSUM 추세 조기경보
  l5_fusion.py    L5 융합·교차검증·에스컬레이션·알림예산
  pipeline.py     StreamProcessor(진입점) — 사용자별 상태·라우팅
  datalog.py      능동학습 수집기
  falleval.py     낙상 평가 공유 헬퍼(스크립트들이 사용)
  datasets/       공개셋 로더(sisfall/weda/umafall/smartfallmm/ppg_dalia/geolife/vitaldb/covid_wearables/synthetic)
  eval/           metrics(평가 지표)
serving/
  api.py          Flask REST(StreamProcessor 래핑) — 기본 0.0.0.0:5001
scripts/          download/train/validate/reverify/benchmark/eval_* (연구·운영 스크립트)
models/           fall_rf.joblib(기본) + fall_rf_wrist/waist.joblib(위치별)
tests/            golden.json(회귀 기준) + (handoff 추가) pytest 스캐폴드
```

---

## 7. 데이터 흐름 예시 (낙상)

```
IMU 스트림 ─▶ ingest_imu
   ├─ FallDetector(source).update(s)
   │     충격>1.8g → 사후수집 → extract_features(23) → FallModel.fall_proba
   │       proba≥th  또는  충격≥3.0g(안전망) → 후보 등록
   │       사후 8s 무활동(std<0.06) → fall_long_lie (EMERGENCY)
   │       무활동 없음 + proba≥th → fall_recovered (CAUTION)
   │       회색지대(0.15≤proba<th) → fall_suspected (CAUTION) → self-check 무장
   ├─ 충격≥2.5g → l3.note_impact (미회복 감시 무장)
   └─ fusion.submit → assess → Assessment
         self-check 무응답 45s → no_response_fall (EMERGENCY)
```
