# `scripts/` — 실행·검증·최적화 스크립트 안내

WidU 파이프라인을 **수급(데이터) → 학습 → 검증 → 최적화 → 벤치마크** 순으로 다루는 스크립트 모음.
각 스크립트의 상세 설명은 같은 이름의 `.md` 파일에 있다(예: [`eval_lodo.py`](eval_lodo.py) → [`eval_lodo.md`](eval_lodo.md)).

> **처음이라면 이 순서로**:
> [`download_data`](download_data.md)(데이터) → [`demo_stream`](demo_stream.md)(전체 흐름 체감) →
> [`train_fall_final`](train_fall_final.md)(모델) → [`reverify`](reverify.md)(자가검증) →
> [`benchmark_vs_baseline`](benchmark_vs_baseline.md)(원본 대비 성능).

---

## 🚀 시작 · 데모
| 스크립트 | 하는 일 |
|---|---|
| [demo_stream](demo_stream.md) | 독거 고령자의 하루를 시뮬레이션하며 5계층 판단을 출력(전체 흐름 체감) |
| [active_learning_demo](active_learning_demo.md) | 능동학습 루프 데모 — 이벤트→캡처→응답라벨→적재→재학습 |

## 📥 데이터 수집
| 스크립트 | 하는 일 |
|---|---|
| [download_data](download_data.md) | 공개 검증 데이터셋(SisFall·PPG-DaLiA·WEDA·UMAFall·SmartFallMM 등) 수급 |

## 🎓 학습 (모델 생성)
| 스크립트 | 하는 일 |
|---|---|
| [train_fall_final](train_fall_final.md) | **최종 배포** 낙상모델 재학습 — 최적 구성으로 전체 데이터 학습(위치별) |
| [train_fall](train_fall.md) | 낙상모델 기본 학습 — SisFall + 누수 없는 증강 파이프라인 |
| [train_fall_combined](train_fall_combined.md) | 다중셋 결합 학습 — 일반화(특히 정밀도) robustness↑ |
| [build_hr_baseline](build_hr_baseline.md) | 개인화 HR 베이스라인(L1) 구축 데모 |

## ✅ 검증 — 계층별 실데이터
| 스크립트 | 하는 일 |
|---|---|
| [validate](validate.md) | 종합 검증 하니스 — 각 계층 + 융합을 실제로 돌려 지표 산출 |
| [verify_preprocess](verify_preprocess.md) | 전처리·증강 자기재검증(누수無·물리 타당성, 실패 시 종료1) |
| [reverify](reverify.md) | **11라운드 재검증** — 누수·임계·서브그룹·서빙·결정성 등 상이 관점 |
| [eval_l1_ppgdalia](eval_l1_ppgdalia.md) | L1 개인화 심박 실검증(PPG-DaLiA 실 손목 HR+활동) |
| [eval_l3_geolife](eval_l3_geolife.md) | L3 위치/행동 실검증(GeoLife 실 GPS — 지오펜스·체류) |
| [eval_l3_immobility](eval_l3_immobility.md) | L3 무활동(12h)+공백리셋 실검증(Stanford 걸음) |
| [eval_l4_resting_hr](eval_l4_resting_hr.md) | L4 안정심박 추세 실검증(Stanford COVID 웨어러블) |
| [eval_wrist](eval_wrist.md) | 손목(실 기기) 낙상 검증(WEDA-FALL 손목·고령) |
| [eval_crossdataset](eval_crossdataset.md) | cross-dataset 일반화 — 다른 기기/인구에서도 유지되나 |

## 🔬 낙상 심화 검증
| 스크립트 | 하는 일 |
|---|---|
| [eval_lodo](eval_lodo.md) | **LODO**(셋 하나 빼고 학습→테스트) 일반화 + 고령 ADL 오탐 probe |
| [eval_augmentation](eval_augmentation.md) | 증강 efficacy A/B(실 SisFall, 피험자분할 동일 폴드) |
| [eval_cascade](eval_cascade.md) | 파형-무관 캐스케이드 효과 — 분류기 미탐을 '충격+무활동'이 복구하나 |
| [eval_elderly_mitigation](eval_elderly_mitigation.md) | 고령 ADL 오탐 처방 — '고령 ADL을 학습에 넣으면 줄어드나' |
| [improve_softfall](improve_softfall.md) | 고령 낙상 recall 개선 — 진단 + 소프트폴 피처 A/B |
| [validate_postfall](validate_postfall.md) | '넘어진 뒤 미회복' 안전망 검증(실 SisFall+사후 정지) |
| [validate_cascade_stream](validate_cascade_stream.md) | 캐스케이드 스트리밍 검증 — 비용(FP) vs 효익(복구) |
| [validate_system_recall](validate_system_recall.md) | 시스템 단위 recall — '결국 가족이 위험을 알았나' |

## ⚙️ 최적화 · 튜닝
| 스크립트 | 하는 일 |
|---|---|
| [optimize_fall_models](optimize_fall_models.md) | 낙상모델 종합 최적화 — 모든 학습구성을 누수없이 비교해 최선 도출 |
| [threshold_sweep_fall](threshold_sweep_fall.md) | 낙상 임계 스윕 — 위치별 운영점(민감도↔정밀도) 선택 |
| [strengthen_wrist](strengthen_wrist.md) | 손목 모델 강화 1단계 — 분류기/정규화 변형을 LODO로 비교 |
| [strengthen_wrist_features](strengthen_wrist_features.md) | 손목 모델 강화 2단계 — 특징 공학(스펙트럼·첨도·피크 등) |
| [strengthen_selfcheck](strengthen_selfcheck.md) | self-check 임계(FALL_PROBA_SOFT) 최적화 — recall↔프롬프트 |
| [l1_persistence_sweep](l1_persistence_sweep.md) | L1 지속시간 최적화 — 속도 vs 오탐(knee 탐색) |
| [l1_fp_techniques](l1_fp_techniques.md) | L1 오탐 억제 기법 스윕(검증된 기법을 PPG-DaLiA로 실측) |
| [l1_activity_source_ab](l1_activity_source_ab.md) | L1 활동 소스 A/B — raw ACC 추정 vs OS 활동인식 대리 |
| [calibrate_l1](calibrate_l1.md) | 활동맥락 임계 보정 — ACC SMA→{REST/LOW/ACTIVE} |

## 📊 벤치마크
| 스크립트 | 하는 일 |
|---|---|
| [benchmark_vs_baseline](benchmark_vs_baseline.md) | **원본(WIDYU-ai) vs WidU** 머리맞대 — 오경보율·응급 탐지(동일 입력) |
| [benchmark_device_configs](benchmark_device_configs.md) | **기기 구성**(워치만/폰만/둘다) 낙상 탐지 — UMAFall 동기 손목·허리, 피험자 분리 |
| [benchmark_transmission_rate](benchmark_transmission_rate.md) | **전송 레이트 강건성** — 50Hz 스펙 충족 시 성능 유지 확인 + 미달 시 손실(워치 민감) |

---

산출물은 대부분 `artifacts/`(JSON 리포트, git 제외)에 저장된다. 경로는 모두 환경 독립([`widu/config.py`](../widu/config.py)의 `ROOT` 기준).
