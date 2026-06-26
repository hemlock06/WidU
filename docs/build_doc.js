// WidU 해설문서 생성기 (docx-js). 주요 분기마다 재실행해 갱신.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageNumber, Header, Footer, PageBreak,
} = require("docx");

const CW = 9360; // content width (US Letter, 1" margins)
const FONT = "Malgun Gothic"; // 한글 렌더
const BLUE = "1F4E79", LBLUE = "D5E8F0", GREY = "F2F2F2", RED = "C0392B";

const border = { style: BorderStyle.SINGLE, size: 1, color: "BBBBBB" };
const borders = { top: border, bottom: border, left: border, right: border };

const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const P = (t, opts = {}) => new Paragraph({ spacing: { after: 120 }, children: [new TextRun({ text: t, ...opts })] });
const Bul = (t) => new Paragraph({ numbering: { reference: "b", level: 0 }, spacing: { after: 40 }, children: [runs(t)].flat() });

// **bold** 인라인 파서
function runs(t) {
  const out = []; const parts = t.split("**");
  parts.forEach((p, i) => { if (p) out.push(new TextRun({ text: p, bold: i % 2 === 1 })); });
  return out;
}

function cell(text, w, o = {}) {
  return new TableCell({
    borders, width: { size: w, type: WidthType.DXA },
    shading: { fill: o.fill || "FFFFFF", type: ShadingType.CLEAR },
    margins: { top: 60, bottom: 60, left: 110, right: 110 },
    children: (Array.isArray(text) ? text : [text]).map((s) =>
      new Paragraph({ children: runs(String(s)), alignment: o.align || AlignmentType.LEFT })),
  });
}

function table(headers, rows, widths) {
  const headRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      borders, width: { size: widths[i], type: WidthType.DXA },
      shading: { fill: BLUE, type: ShadingType.CLEAR },
      margins: { top: 60, bottom: 60, left: 110, right: 110 },
      children: [new Paragraph({ children: [new TextRun({ text: String(h), bold: true, color: "FFFFFF" })] })],
    })),
  });
  const body = rows.map((r, ri) => new TableRow({
    children: r.map((c, i) => cell(c, widths[i], { fill: ri % 2 ? GREY : "FFFFFF" })),
  }));
  return new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, rows: [headRow, ...body] });
}

const today = "2026-06-24";

const children = [];
// ---- 표지 ----
children.push(new Paragraph({ spacing: { before: 1200, after: 80 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "WidU", bold: true, size: 72, color: BLUE })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  children: [new TextRun({ text: "독거 고령자 실시간 위급상황 탐지 AI", bold: true, size: 32 })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 },
  children: [new TextRun({ text: "설계·구현 해설문서 / 의사결정 기록", size: 26, color: "555555" })] }));
children.push(table(["항목", "내용"], [
  ["문서명", "WidU 해설문서"],
  ["버전", "v0.20 (원본 vs WidU 머리맞대 검증 — 통째 교체 근거)"],
  ["작성일", today],
  ["대상 프로젝트", "WIDYU 앱 — 응급알람 기능 (SCRUM-49 / SCRUM-75)"],
  ["저장 위치", "프로젝트 루트(경로는 환경 독립 — config.ROOT 상대경로)"],
  ["갱신 규칙", "주요 분기(설계 변경·계층 추가·검증 결과)마다 §10 의사결정 로그에 추가"],
], [2400, 6960]));
children.push(new Paragraph({ children: [new PageBreak()] }));

// ---- 1 ----
children.push(H1("1. 문서 목적"));
children.push(P("이 문서는 WidU AI 파이프라인의 모든 설계 의사결정과 근거, 구현 현황, 검증 결과를 기록한다. 코드(repo 루트)와 1:1로 대응하며, 주요 분기마다 갱신한다. WIDYU 팀 자료(Jira 307이슈·Confluence 100페이지·Figma)를 전수 검토한 결과에 기반한다."));

// ---- 2 ----
children.push(H1("2. 프로젝트 배경 (확인된 사실)"));
children.push(Bul("**제품**: 독거 고령자–부양자녀 연동 돌봄 앱. 응급알람·목표/리워드·위치 공유. 응급알람 월 9,900원 구독."));
children.push(Bul("**현재 배포된 응급**: 워치 심박 → 심박수 이상치 판별 API(**SCRUM-287 = MA+고정임계, GitHub 레포**) → 위험도 판별(SCRUM-266) → FCM. 위치 안전구역 이탈 150m(SCRUM-282)."));
children.push(Bul("**AI 에픽 SCRUM-75**: VitalDB 샘플링(완료) → 심혈관/호흡 베이스라인 → 개인화. 현재 SCRUM-179 '실제 심박수 분석' 아이디어 단계."));
children.push(Bul("**팀의 피벗(SCRUM-84)**: 데이터 확보 한계로 '심박수 실시간 분석'으로 방향 전환 — 본 설계와 동일 결론."));
children.push(Bul("**UI(Figma)**: 심박 3-상태(안정/주의/연결불가)·이상감지 히스토리·위급시 자동통화/잠금화면·안심구역 반경 — 디자인도 HR+위치 단일축으로 수렴."));

// ---- 3 ----
children.push(H1("3. 수렴된 데이터 계약"));
children.push(P("Confluence '건강 데이터 수집 가능성 조사' 실측. 이 표가 설계의 전제다.", { italics: true }));
children.push(table(["신호", "실시간성", "주기", "AI 활용"], [
  ["심박수(bpm)", "○ 상시", "1Hz", "급성 심혈관·실신"],
  ["가속도+자이로", "○ 상시", "50~200Hz", "낙상·활동맥락"],
  ["위치(GPS)", "○ 준실시간", "이벤트", "안전구역·배회·무활동"],
  ["SpO₂", "✕ 기록형", "20~40분", "느린 추세(조기경보)"],
  ["체온", "✕ 기록형", "수면시", "느린 추세"],
  ["ECG", "✕", "수동", "사실상 배제(갤럭시 미제공)"],
], [2200, 1700, 1700, 3760]));
children.push(P("→ 핵심: 실시간 응급 축은 HR + 낙상(IMU) 둘뿐. SpO₂·체온은 응급 트리거 불가 → 조기경보로 강등.", { bold: true }));

// ---- 4 ----
children.push(H1("4. 핵심 설계 의사결정"));
const decisions = [
  ["D1", "실시간 축을 HR+IMU로 한정, SpO₂/체온은 조기경보로 강등", "SpO₂·체온은 실시간 측정 불가(20~40분/수면). 응급 트리거로 쓰면 미탐/오탐."],
  ["D2", "5계층 분리(L0~L5)", "위급은 속도(초~일)·신호종류가 다른 사건의 혼합. 단일 모델이 아니라 목적별 탐지기+융합."],
  ["D3", "L1=개인화+맥락게이팅, 딥러닝은 보류", "단일 1Hz 스칼라에서 딥러닝 이득 작음. 개인화·맥락·지속성이 정확도·오경보 최대 개선."],
  ["D4", "L2 낙상을 최우선 신규 AI로", "IMU가 이미 수신 중 + 공개 라벨(SisFall 등) 존재 → '데이터 한계' 정면 돌파, 독거노인 임팩트 최대."],
  ["D5", "낙상 2단계 배터리 캐스케이드", "상시 고주파 스트리밍은 배터리 자살. 저전력 충격 트리거 시에만 윈도우 분류."],
  ["D6", "낙상 확정 = 충격 + 사후 무활동", "앉기/눕기 등 ADL 오탐 억제. '못 일어남(long-lie)'을 위급으로."],
  ["D7", "L5 오경보 억제 규칙", "운동맥락 단독 고심박 → 격하 / 심박이상+무활동 → 위급 격상. 알림 예산으로 보호자 신뢰 보호."],
  ["D8", "프로젝트를 D 드라이브로", "N:(클라우드 MYBOX) 용량 제약 회피."],
  ["D9", "검증=공개셋(컴포넌트)+POC(통합) 이중구조", "WIDYU 정확한 설정의 단일 공개셋은 없음. 컴포넌트는 공개셋, 통합은 금천에이스요양원 POC 피드백 라벨."],
  ["D10", "다운샘플(200→50Hz) 전 안티앨리어싱(Butterworth) 필수", "단순 선형 리샘플은 40Hz→10Hz 폴딩. 저역통과 후 리샘플로 에일리어싱 방지(검증: 폴딩 21.5→0.8)."],
  ["D11", "학습/서빙 윈도우 규약 일치(충격 pre_frac=0.75)", "학습=피크중심 / 서빙=충격 버퍼끝 이면 train/serve skew. 서빙도 충격 후 사후맥락 수집 후 분류 → 동일 규약."],
  ["D12", "증강: 분할 이후 학습셋만 / 회전 bound / time_warp 제외", "분할 전 증강=누수. 전체 SO(3) 회전=손목 비물리. 회전각 손목±70°·폰±30°. time_warp는 충격 스파이크 훼손 → 제외."],
  ["D13", "워치+폰 이중 IMU(결정수준 교차검증)", "폰(신체중심)은 낙상에 워치보다 정밀하나 간헐적(책상/충전) → 필수 아닌 보강. 두 기기 독립 회전(같은 R 금지)."],
  ["D14", "전처리·증강 11패스 자기재검증 통과", "단위·안티앨리어싱·윈도우일치·피험자누수·증강순서·회전물리·건전성·균형·재현성·특징일치·독립회전."],
  ["D15", "실 SisFall로 낙상모델 학습·배포(F1 0.983)", "피험자분할 CV. 배포 fall_rf.joblib을 합성→실데이터로 교체. 합성 1.0은 폐기."],
  ["D16", "증강 efficacy 실측 = 허리에선 미미(+0.3%)", "회전증강의 진가는 손목 방향불변 → 손목셋으로 재확인 필요. SisFall(허리)만으론 결론 보류."],
  ["D17", "감사 버그 3건 교정 + IMU 입력 계약 명문화", "VitalDB gzip·L3 무활동 공백리셋·SisFall URL/중첩zip. 서버는 IMU를 50Hz로 받음(온디바이스 안티앨리어싱 다운샘플)."],
  ["D18", "낙상 분류 임계 0.5→0.4(안전 우선)", "재검증 R4: 0.4에서 민감도 0.982·정밀도 0.984. 사후 무활동 게이트가 정밀도 보강 → 미탐 최소 우선."],
  ["D19", "고령 recall 0.83은 L2 천장 — L3가 안전망", "임계·가중으로 미해결(실측). 고령 소프트폴≈ADL. 다층(L2충격+L3무활동)으로 방어, 결합 recall은 POC 검증. 단일 충격모델 과신 금지."],
  ["D20", "중간지평 '넘어진 뒤 미회복' 안전망 추가", "충격(≥2.5g)+3분 무활동→보호자 알림. 고령 오분류 낙상 회수 0.825. 단 충격수준 구별불가→보수적 등급(자동119 아님)+POC FP검증. 손목 자세불가→폰 IMU가 정밀도 길."],
  ["D21", "손목(실 기기) 검증 — WEDA-FALL 확보", "민감도 0.91·소프트폴(고령) recall 0.90. ★앞선 '고령 0.83'은 허리(SisFall) 아티팩트로 정정. 정밀도 0.73이 손목 약점."],
  ["D22", "위치별 전용 낙상 모델(워치=손목·폰=허리)", "허리→손목 전이 민감도 0.60(40% 미탐) 실측 → 한 모델 양위치 금지. watch=WEDA, phone=SisFall 분리 로딩."],
  ["D23", "cross-dataset 일반화 검증(UMAFall)", "민감도는 전이됨(손목 0.90·허리 0.99) → 단일셋 과적합 아님. 정밀도는 기기별 하락 → 결합학습·기기보정·POC."],
  ["D24", "다중셋 결합 모델 배포(3셋·2위치)", "손목=WEDA+UMAFall, 허리=SisFall+UMAFall. 다양성↑로 일반화 robustness. 혼합폴드 CV 손목 0.93/허리 0.98."],
  ["D25", "L1(심박) 실데이터 검증(PPG-DaLiA)", "전제(HR 맥락분리) 검증, 게이팅이 고정임계 절반 오탐. 단 2.06/hr 과다→배포불가. 손목 ACC 활동천장 0.54·SMA보정 역효과 → 워치 활동상태가 답."],
  ["D26", "네이티브 낙상 API 활용 + IMU모델 재포지셔닝", "워치 네이티브(애플 CMFallDetectionManager 엔타이틀먼트·삼성 Health Services FALL_DETECTED)가 실 낙상 검출 우월. 우리 모델=폴백, 핵심가치=가족라우팅·미회복·HR/위치 융합. 워치 컴패니언 앱 필요."],
  ["D27", "기기 가용성 매트릭스(워치+폰 이중 운용)", "ingest_fall_event(네이티브)·폰단독 wear 자동전환·워치+폰 교차검증. 둘 운용=정확도↑(미탐↓·오탐↓). 폰단독은 폰 미착용 공백→워치 주력."],
  ["D28", "L1 오탐 해결 — 검증기법 적용", "긴 지속+안정시에만 → PPG-DaLiA 오탐 2.06→0(둔감 아님: 지속 이상은 잡음). 애플/ICU/Stanford 근거. L0=급성·L1=소프트 분리. sensitivity는 POC 확인."],
  ["D29", "L1 지속시간 최적화 = 3분(180s)", "정밀 스윕: 오탐 0 knee=115초(1.9분). 애플 10분·초기 5분은 과함. knee가 아니라 180s 채택 이유=36h로 0 증명불가(칼날 knee)+L1은 소프트층(급성은 L0 30초)+마진=신뢰. 바닥선 150s."],
  ["D30", "단독 무활동(12h) 격하 — EMERGENCY→CAUTION", "L3 실검증(Stanford 걸음): 거친 활동신호로 단독 12h 규칙이 3.5/년 오발 → 알람피로. 충격·이상심박 동반 시에만 위급, 단독은 CAUTION(본인확인·부드러운 push). L5 교차검증 철학과 일치."],
  ["D31", "데이터 표적확장(SmartFallMM) + LODO + 고령 처방", "무차별 수집 거부, 새 축 1개만. LODO=미지 손목 F1 0.74(CV 0.98은 낙관)·허리 0.90 → 워치 약점 확인. 고령 ADL 오탐 24%→처방(고령ADL 학습) 9.5%. 표적데이터는 답이나 고령 낙상 recall은 POC 필요."],
  ["D32", "낙상모델 종합 최적화 — 손목 재학습+위치별 임계, 허리 유지", "모든 구성 LODO/고령FP 비교. ★손목=C3 재학습+임계0.30(고령FP 0.42→0.15·민감도 0.75→0.82, 구배포 양축 압도). ★허리=레거시 유지(SMM 추가가 악화, '더 모으면 좋다' 반례). reverify 무회귀."],
  ["D33", "손목 강화 — 특징 공학(9개 추가)", "분류기/정규화는 실패(데이터한계 확인)·특징공학은 성공. 스펙트럼·첨도·피크 등 → 손목 LODO F1 0.713→0.744·고령FP 0.151→0.135, 허리 무해. 공용 extract_features 23특징, 3모델 재학습. 비용=FFT(충격시에만)."],
  ["D34", "POC 대안 — 파형-무관 캐스케이드 + 네이티브 위임", "#2 분류기-독립 hard-impact(≥3.0g)+8초무활동→fall_long_lie(현실FP 0·최악 4.2%, 효익 미측정=데이터부재). #1 네이티브 위임(애플/삼성 실낙상 학습, ingest_fall_event). 둘 다 recall갭 완충(insurance)이지 측정된 개선 아님. reverify 무회귀."],
  ["D35", "능동 확인 루프(A) + 시스템 recall(B) — 지표 재정의", "데이터 없이 '낙상 파형 recall' 대신 '가족이 위험을 앎(시스템 recall)'을 올림. A=회색지대→self_check→45초무응답→격상(사람=정답). B=held-out 시스템 recall 0.69(self-check가 133/200 복구, A없으면 0.03). UX=ADL 16% 프롬프트(오경보 아님). 잔여=저충격 소프트폴(데이터 필요)."],
  ["D36", "self-check 임계 검증 → 0.15 유지(과적합 회피)", "LODO 스윕(3셋평균): soft 0.15가 recall(0.957)·배포프롬프트(9.2%) 균형 knee. 낮추면 프롬프트 2배·recall +0.9%p뿐 → 변경 안 함. 분석이 기존 설계 검증. 억지 튜닝=과적합. 잔여 저충격 소프트폴은 데이터 벽."],
  ["D37", "능동학습 데이터 엔진 — 배포=실데이터 수집", "self-check 응답=라벨. 이벤트→10초 IMU 캡처→respond_ok(오경보)/confirm_incident(낙상) →디스크 적재→재학습. 동의 게이트(기본 off). 루프 닫힘(수집→23특징→train_fall_final). POC/FARSEEING 없이 실 고령 낙상 확보하는 자력 경로. datalog.py·serving 3엔드포인트."],
  ["D38", "원본(WIDYU-ai) vs WidU 머리맞대 검증 → 통째 교체", "동일 입력: 오경보 원본 54.6/h vs WidU 0.5/h(110배). 응급탐지 무승부(둘다)나 원본은 과발화로 잡음(HR 65 정상서도 발화=54/h와 동일현상). 원본 속도 우위는 알람피로로 무의미. 낙상=원본 0. 데이터가 통째 교체 지지."],
];
children.push(table(["#", "결정", "근거"], decisions, [700, 3400, 5260]));

// ---- 5 ----
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(H1("5. 코드베이스 구조 (repo 루트)"));
children.push(table(["경로", "역할"], [
  ["widu/types.py", "공통 데이터 계약(샘플·판단 타입)"],
  ["widu/gating.py", "품질 게이트·활동맥락 추정·아티팩트"],
  ["widu/l0_safety.py", "L0 결정적 안전룰(임상 임계+지속성)"],
  ["widu/l1_hr.py", "L1 개인화 심박(맥락조건부 z, 콜드스타트 prior)"],
  ["widu/l2_fall.py", "L2 낙상(특징추출+충격 캐스케이드+RandomForest)"],
  ["widu/l3_behavior.py", "L3 지오펜스·무활동·배회"],
  ["widu/l4_trend.py", "L4 느린추세(CUSUM 조기경보)"],
  ["widu/l5_fusion.py", "L5 융합·등급·에스컬레이션·오경보 억제"],
  ["widu/pipeline.py", "StreamProcessor(전 계층 통합)"],
  ["widu/datasets/*", "SisFall·PPG-DaLiA·VitalDB 로더 + 합성"],
  ["widu/eval/metrics.py", "민감도·정밀도·TTA·오경보/일"],
  ["scripts/*", "download_data·train_fall·build_hr_baseline·validate·demo_stream"],
  ["serving/api.py", "Flask 서빙(SCRUM-287 후계)"],
], [3200, 6160]));

// ---- 6 ----
children.push(H1("6. 검증 결과 (v0.1 현재)"));
children.push(P("빌드하며 실제로 실행해 확인(합성 데이터 — 실 데이터·POC로 재측정 예정).", { italics: true }));
children.push(table(["항목", "결과"], [
  ["파이프라인 스모크", "정상→위급 전이·미착용 처리 OK"],
  ["낙상 end-to-end", "충격→무활동 9s → 위급·auto_call OK"],
  ["데모(하루)", "산책 중 128bpm → 정상(운동맥락 억제) / 낙상 → 위급"],
  ["validate.py HR(합성)", "이벤트 recall 1.0 · 오경보 에피소드 0"],
  ["낙상(실 SisFall)", "피험자분할 CV F1 0.983 (배포 모델)"],
  ["Flask API", "정상→위급(guardian_push)·위치 융합 OK"],
], [3400, 5960]));

children.push(H2("6-1. 실데이터 검증 (v0.3)"));
children.push(P("합성 1.0은 상한일 뿐이라 실 공개데이터로 교체. SisFall 전체(4505윈도우·38명) 피험자분할 5-fold CV.", { italics: true }));
children.push(table(["조건", "민감도", "특이도", "정밀도", "F1"], [
  ["증강 없음", "0.974", "0.990", "0.986", "0.979"],
  ["증강 있음(n_aug=2)", "0.975", "0.994", "0.990", "0.983"],
  ["Δ(증강−무)", "+0.002", "+0.003", "+0.005", "+0.003"],
], [2760, 1650, 1650, 1650, 1650]));
children.push(Bul("**낙상모델은 실데이터에서 F1 0.98**(피험자 독립) — 합성 1.0이 아닌 현실 수치. 최중요 피처=충격 시 자세변화(orient_change)."));
children.push(Bul("**증강 효과는 +0.3%로 미미**(주로 오탐↓). 단 SisFall은 **허리**(≈폰/신체중심) → 회전증강의 진가(손목 방향불변)는 여기서 안 드러남. **손목셋(FallAllD/SmartFall)로 별도 확인 필요**(미완 갭)."));
children.push(Bul("**VitalDB 실 API 접근 복구**(gzip 디코드 교정) — 트랙 486,449개·HR 6,387개. 임계 보정·생리 타당성에 활용."));

children.push(H2("6-2. 10라운드 재검증 결과 (페이즈 전환 규칙)"));
children.push(P("주요 페이즈 전환마다 10개 상이 관점으로 재검증(scripts/reverify.py). 11/10 중 1건 ISSUE 적발.", { italics: true }));
children.push(table(["라운드", "결과", "요지"], [
  ["R1 재현성", "OK", "폴드간 F1 0.983±0.008"],
  ["R2 누수탐색", "OK", "피험자겹침0·OOF완전·증강 train만"],
  ["R3 라벨건전성", "OK", "낙상 5.49>ADL 2.12g·고령15명"],
  ["R4 임계최적성", "OK", "th0.5 민감도0.977 → 0.4 채택(0.982)"],
  ["R5 고령 recall", "⚠ ISSUE", "고령 0.827 vs 성인 0.988 — 타깃 미탐"],
  ["R6 실전처리", "OK", "안티앨리어싱·윈도우 0.76"],
  ["R7 서빙검출(fall)", "OK", "실 낙상 스트리밍 0.970"],
  ["R8 서빙오탐(ADL)", "OK", "3.0%(무활동 게이트로 추가억제)"],
  ["R9 결정성", "OK", "동일 seed 일치"],
  ["R10 회귀", "OK", "11패스 통과"],
  ["R11 고령가중", "OK", "가중학습 효과 제한적(미채택)"],
], [2200, 1500, 5660]));
children.push(P("★ 가장 중요한 발견 — 고령 recall 0.83", { bold: true, color: RED }));
children.push(Bul("집계 F1 0.983이 **고령자(타깃) recall 0.827을 가렸음**(성인 0.988). 고령 낙상 17% 미탐."));
children.push(Bul("**임계 하향(0.4·0.3)도 고령 가중학습(4배)도 미해결**(둘 다 실측). 근본 원인: 고령 소프트폴이 충격 피처상 ADL과 닮음 + 고령 15명 얇은 데이터."));
children.push(Bul("→ **다층 설계(L2 충격 + L3 사후 무활동)가 옳았던 증거.** L2 단독은 고령 소프트폴을 놓치지만 L3 장기무활동이 안전망. **L2+L3 결합 recall은 실데이터/POC로 검증 필요.**"));
children.push(Bul("처방: ① 임계 0.4 채택(완) ② 소프트폴 전용 피처(느린 onset) ③ 실 고령 낙상데이터·손목셋 ④ POC에서 L2+L3 결합 recall 측정."));

children.push(H2("6-3. 중간지평 '넘어진 뒤 미회복' 안전망 (v0.5)"));
children.push(P("고령 미탐 처방 실행. 진단: 충격 트리거율 고령 0.933(소프트폴 7%뿐)·분류 recall 0.827 → 임계·고령가중·소프트폴피처 3정공법 모두 실측 실패(Δ≈0). 남은 길은 시간축.", { italics: true }));
children.push(Bul("**메커니즘**: 충격(≥2.5g) 발생 → 3분간 무활동 지속 → '미회복' 경보. L2 fall_long_lie(8s)와 L3 무활동(12h) 사이 공백을 메움. 충격 직후 grace(10s)로 안정화 모션 무시."));
children.push(Bul("**검증(실 SisFall+정지 시뮬)**: 고령 낙상 회수율 **0.825**. 단 충격ADL도 정지가정 시 0.975 발화 → **충격 수준으론 낙상·격한ADL 구별 불가**, 시간축(못 일어남)에만 의존."));
children.push(Bul("**정직**: 진짜 정밀도(앉고 쉬는 정상 vs 못 일어남)는 **POC로만** 확정. **손목 워치는 자세(누움/앉음) 구별 불가**(팔 위치 자유) → 정밀도 개선의 길은 **폰(신체중심) IMU 보강**."));
children.push(Bul("**보수적 설계**: EMERGENCY지만 자동119 아닌 **보호자 알림(guardian_push)** — FP 불확실성 대비. 회귀 재검증 10/11 무결."));

children.push(H2("6-4. 손목(실 기기) 검증 + 위치별 모델 (v0.6)"));
children.push(P("오픈소스 WEDA-FALL(Fitbit Sense 손목·고령·50Hz, 낙상 F05~08='앉다가/실신'=고령 소프트폴) 확보 → 우리 실제 기기(손목)를 처음 실 손목 데이터로 검증.", { italics: true }));
children.push(table(["검증", "민감도", "정밀도", "F1", "비고"], [
  ["손목 자체 CV(WEDA)", "0.91", "0.73", "0.81", "소프트폴(고령) recall 0.90"],
  ["허리(SisFall)→손목 전이", "0.60", "0.62", "0.61", "40% 미탐 — 위치 불일치"],
], [2700, 1450, 1450, 1300, 2460]));
children.push(Bul("**★ '고령 recall 0.83'은 허리 데이터 아티팩트였음.** 실 손목+고령 데이터에 손목 모델을 쓰면 소프트폴 recall **0.90** — 우리 기기에선 훨씬 낫다."));
children.push(Bul("**위치별 전용 모델 필수**: 허리 학습모델을 손목에 쓰면 민감도 0.60(40% 미탐). → **워치=WEDA(손목)·폰=SisFall(허리)** 분리. 이중 IMU 설계가 비로소 완성."));
children.push(Bul("손목 약점 = 정밀도 0.73(손목은 많이 움직여 오탐↑) → 미회복 net + 폰 교차검증으로 보완."));
children.push(Bul("남은 갭: WEDA도 시뮬레이션 낙상(실 낙상 아님)·정밀도/오탐은 POC 필요. PPG-DaLiA(L1)·다중셋 일반화는 다음."));

children.push(H2("6-5. Cross-dataset 일반화 + 다중셋 결합 모델 (v0.7)"));
children.push(P("단일셋 과적합 여부 점검 — UMAFall(다부위·다른 기기 SensorTag·20Hz·다른 인구)로 전이 측정.", { italics: true }));
children.push(table(["전이", "자체CV 민감도", "전이 민감도", "정밀도(자체→전이)"], [
  ["손목 WEDA→UMAFall", "0.938", "0.904", "0.78 → 0.66"],
  ["허리 SisFall→UMAFall", "0.979", "0.989", "0.99 → 0.89"],
], [3000, 2100, 1800, 2460]));
children.push(Bul("**★ 안전직결 민감도가 전이됨**(손목 0.90·허리 0.99) → 단일셋 헤드라인은 **과적합 허상 아님, robust**. 다른 기기·인구·레이트에도 '낙상 안 놓침'이 유지."));
children.push(Bul("**정밀도는 기기별 하락**(손목 0.78→0.66) — 미지 기기서 오탐↑. 덜 치명적 방향(오탐)이고 미회복 net·폰 교차검증·결합학습이 보완."));
children.push(Bul("**처방: 다중셋 결합 모델 배포** — 손목=WEDA+UMAFall(44명, 혼합폴드 CV 민감도 0.93·F1 0.82), 허리=SisFall+UMAFall(56명, F1 0.98). **낙상이 3개 공개셋·2위치로 검증.**"));

children.push(H2("6-6. L1(심박) 실데이터 검증 — 제품 주 신호 (v0.8)"));
children.push(P("지금껏 L1은 합성/로직만 검증 → 정작 제품 헤드라인인 '심박 응급알람'의 빈 곳. PPG-DaLiA(15명·36h·실 손목 HR+활동)로 첫 실검증. 건강 피험자 → 모든 경보=오탐(FP).", { italics: true }));
children.push(table(["항목", "값", "의미"], [
  ["맥락별 HR", "REST<LOW<ACTIVE 일관", "전제(맥락분리) 검증됨"],
  ["오탐/시간(맥락게이팅)", "2.06", "고정임계 4.89의 절반"],
  ["오탐/시간(고정임계)", "4.89", "맥락 무시 룰 = 사용불가"],
  ["ACC 활동추정 일치", "0.68", "약함 — 손동작 혼입"],
], [3000, 2000, 4360]));
children.push(Bul("**핵심 전제는 검증됨**: 실데이터에서 HR이 활동맥락별로 명확히 분리(REST 66 / ACTIVE 91 등). 맥락게이팅이 고정임계 대비 오탐 절반."));
children.push(Bul("**★그러나 2.06/시간(≈하루 50회)은 제품엔 과다 → L1 현 튜닝 배포 불가.** ('오탐률 미지' 갭의 실측 답.)"));
children.push(Bul("**약한 고리 = 손목 ACC 활동추정**(천장 ~0.54, 손동작이 활동 흐림). **SMA 임계 보정은 역효과**(일치도 0.68→0.70 올랐으나 오탐 2.06→2.89 악화 — '일치도'≠'오탐' 목표). → SMA 튜닝으론 못 고침."));
children.push(Bul("**진짜 처방**: ① raw ACC 대신 **워치 내장 활동상태**(HealthKit/Health Connect 운동세션·걸음수) 사용 ② persistence·아티팩트 거부(accuracy 플래그) 강화 ③ FP 지표로 검증. 낙상(L2)만큼 성숙시키려면 추가 작업 필요."));

children.push(H2("6-7. 네이티브 낙상 API 재정렬 (전략)"));
children.push(P("애플/삼성 워치엔 이미 낙상감지가 내장. 팀의 '불가능' 결론은 폰 API 한정으로만 맞음.", { italics: true }));
children.push(Bul("**폰 API(Health Connect/HealthKit)**: 실시간 낙상 ✗ (HealthKit numberOfTimesFallen은 1~60분 지연·확인된 낙상만 집계). 팀이 본 게 이것."));
children.push(Bul("**워치 네이티브 API**: 실시간 낙상 ○ — 애플 **CMFallDetectionManager**(watchOS, 엔타이틀먼트 신청 필요) / 삼성 **Health Services FALL_DETECTED**(Wear OS). 단 **워치 컴패니언 앱**(watchOS+Wear OS) 필요 — Flutter 폰앱만으론 불가."));
children.push(Bul("**의미**: 네이티브는 수백만 실 낙상으로 학습·온디바이스 → **순수 검출론 우리 시뮬 모델보다 우월**. → 하이브리드: **네이티브=검출**, **우리 파이프라인=가족 라우팅·미회복 안전망·HR/위치 융합·폴백**(네이티브는 event/SOS만 줌)."));
children.push(Bul("우리 IMU 낙상모델 재포지셔닝: 주력 검출기가 아니라 **폴백+융합 레이어**. 같은 원칙이 L1 활동에도 적용(워치 기능 받아쓰기 > raw 재발명)."));

children.push(H2("6-8. 기기 가용성 매트릭스 — 워치+폰 이중 운용 (v0.9)"));
children.push(P("가용 기기에 따라 자동 적응(graceful degradation). 둘 다 운용해 정확도↑.", { italics: true }));
children.push(table(["상황", "동작", "신뢰도"], [
  ["워치 + 폰", "네이티브 낙상 + 폰 우리모델 → 교차검증", "최고"],
  ["워치만", "네이티브 낙상(없으면 손목모델 폴백)", "높음(상시 가용)"],
  ["폰만(워치 없음)", "폰 우리모델 — 활동/무활동도 폰으로 자동 전환", "부분(폰 미착용 공백)"],
  ["둘 다 미착용", "실시간 낙상 불가", "공백"],
], [2400, 4600, 2360]));
children.push(Bul("구현: `ingest_fall_event(source='watch')` 네이티브 입력 경로 + `_wear_source()` 폰-단독 자동 전환 + L5 '워치+폰 교차확인'. 스모크 3종 통과."));
children.push(Bul("**둘 다 운용 = 정확도↑**: 한쪽 미탐을 다른 쪽이 보완(미탐↓), 둘 다 동의 시 고신뢰(오탐↓)."));
children.push(Bul("**정직**: 폰-단독은 **폰이 몸에 있을 때만** — 화장실·침실(낙상 多 장소)에 폰 안 들고 가면 공백. → 워치가 주력, 폰은 보강·폴백."));

children.push(H2("6-9. L1 오탐 해결 — 검증된 기법 적용 (v0.10)"));
children.push(P("웹 딥리서치: 이 문제(웨어러블 심박 실시간 알람 오탐)는 상업제품·ICU(알람피로 수십년)·학계가 이미 풀었음 — '더 똑똑한 모델'이 아니라 보수적 시스템.", { italics: true }));
children.push(table(["검증된 기법", "근거(실측)"], [
  ["긴 지속시간", "애플 HR알림=10분+비활동 / ICU 15~19초 지연→오탐 50~67%↓"],
  ["안정시에만", "Stanford RHR-diff·HROS-AD: 활동 중 무시, 쉴 때만"],
  ["신호품질·아티팩트 거부", "BSN: 9.58%→1.43%"],
  ["멀티파라미터 확증", "PhysioNet CinC 2015 챌린지"],
  ["사람 확인/취소 창", "애플·의료알람 30초 취소 → 보호자 오탐≈0"],
], [2700, 6660]));
children.push(P("적용(① 긴 지속, ② 안정시에만) → PPG-DaLiA(15명·36h) 오탐 2.06→0.", { bold: true }));
children.push(P("지속시간 최적화(속도 vs 오탐): 길수록 오탐↓이나 알림 지연↑ → 최선=오탐 0 유지하는 최단.", { italics: true }));
children.push(table(["지속시간", "오탐/시간", "알림지연"], [
  ["60s(1분)", "0.14", "1분"],
  ["90s(1.5분)", "0.03", "1.5분"],
  ["120s(2분)", "0.00", "2분 (knee)"],
  ["180s(3분)", "0.00", "3분 (배포·마진)"],
  ["300s(5분)", "0.00", "5분 (과함)"],
], [2400, 2000, 4960]));
children.push(Bul("**오탐 0 정확한 knee = 115초(1.9분)** — 정밀 스윕(90~110s에 끈질긴 1건이 115s에서 소멸). 애플 10분·초기안 5분은 과함. **배포=3분(180s)**: 115s 절벽 위 65초 의도적 마진."));
children.push(Bul("**왜 knee(115s)가 아니라 180s인가**: ① 36h로는 '0' 증명 불가(통계적 ≤0.08/hr, knee가 칼날) ② L1은 소프트층 — 급성은 L0가 30초에 잡으므로 65초 단축 이득 미미 ③ 마진=보호자 신뢰. 바닥선은 150s(2.5분)."));
children.push(Bul("**둔감 아님(스모크 검증)**: 6분 지속 안정빈맥 → 잡음, 1분·운동 중 → 무시. 진짜 지속 이상은 유지."));
children.push(Bul("**L0=급성(하드룰 30s)·L1=소프트(긴지속 300s) 분리 완성.** 급성(실신·서맥·빈맥)은 L0가 짧게 잡고, 미묘한 개인 이탈은 L1이 길게 확증."));
children.push(Bul("**정직**: '0 오탐'의 sensitivity(진짜 미묘한 이상을 놓치지 않는지)는 anomaly 라벨(POC)로 최종 확인 필요 — 단 급성은 L0가 커버하므로 안전."));

children.push(H2("6-10. L3(행동·위치)·L4(추세) 실데이터 검증 (v0.12)"));
children.push(P("마지막 미검증 영역(이전엔 합성/로직만) — 실 공개셋 2종으로 검증. GPS·추세엔 '응급' 라벨이 없어 L1과 같은 정직한 방법론(실 오탐율 + 주입 민감도, 또는 결정적 기하 sanity).", { italics: true }));
children.push(P("L4 안정심박 추세 — Stanford COVID 웨어러블(118명·9,041 person-day, 분당 HR+걸음).", { bold: true }));
children.push(table(["측정", "결과", "해석"], [
  ["실 경보율(FA 상한)", "0.95/월(중앙 0.77)·21%는 0건", "INFO(조기경보)로 비-스팸 수준"],
  ["주입 민감도 Δ+8(임계)", "탐지 0.82", "감염형 상승의 임상 구간"],
  ["주입 민감도 Δ+10 / +12", "0.92 / 0.97", "상승 ~1일 후 발화(빠름)"],
], [2700, 2600, 4060]));
children.push(Bul("L4는 INFO 조기경보로 적정 — 임상 크기(+8~10bpm, Stanford 선례)에서 잘 잡고 헛경보 적음. RHR 추출 생리타당(중앙 70~78bpm, 일변동 2~7)."));
children.push(P("L3 무활동(12h)+공백리셋 — Stanford 걸음(119명·9,713 person-day).", { bold: true }));
children.push(Bul("★**실데이터 발견**: 걸음 기반 '정지' 신호로는 12h 규칙이 **3.5회/년 오발**(활동신호가 간헐적 0/부재인데 HR은 계속). 걸음결측→정지 오인 아티팩트 교정(4.81→3.5), 잔여는 '착용+무보행 장시간'."));
children.push(Bul("→ **조치(D30)**: 단독 무활동을 EMERGENCY→**CAUTION**으로 격하(L5). 충격·이상심박 동반 시에만 위급. 실배포 활동맥락=가속도 미세움직임(걸음보다 훨씬 자주 리셋)이라 실제 오발은 이 상한보다 낮음."));
children.push(P("L3 지오펜스·체류·배회 — GeoLife 실 GPS(48명).", { bold: true }));
children.push(table(["측정", "결과", "해석"], [
  ["staypoint/일(중앙)", "1.52", "실 체류지 정상 추출"],
  ["안전구역 이탈/일(중앙·p90)", "0.82 · 2.31", "'하루 한 번 외출' 상식범위 — 임계 타당"],
  ["야간배회", "6명 0건·총 1303", "GeoLife=야간활동 많은 젊은층 → 고령 특이성은 측정불가(갭)"],
], [2900, 2400, 4060]));
children.push(Bul("지오펜스 기하 검증(이탈 episode=전이당 1건; per-sample 850건은 카운팅 버그였음→교정). 임계(이탈 150m·체류 10분)가 실 이동에서 합리적 빈도."));
children.push(Bul("**정직한 갭**: 두 셋 모두 고령자 아님(Stanford 일반 성인·GeoLife 젊은 연구자). 고령 특이성·실 응급 라벨은 POC 필요. 단 알고리즘 기하·임계·오탐경향은 실데이터로 확인."));

children.push(H2("6-11. 데이터 표적 확장 + LODO 일반화 + 고령 처방 (v0.13)"));
children.push(P("\"데이터 최대한 끌어모으기\"에 대한 비판적 답: 양이 아니라 '처음 보는 분포에 일반화되나'가 정직한 척도. 무차별 수집 대신 새 축을 더하는 SmartFallMM(Texas State, 손목+엉덩이, 젊은+고령 65.5세) 1개만 추가 → 위치별 3소스로 leave-one-dataset-out(LODO) 가능.", { italics: true }));
children.push(P("LODO: 셋 1개를 통째로 빼고 학습→빼둔 셋 테스트(=미지 출처 일반화). in-domain CV(0.98)와의 격차=새 출처 페널티.", { bold: true }));
children.push(table(["위치(held-out 평균)", "민감도", "정밀도", "F1"], [
  ["손목(워치=주력)", "0.856", "0.658", "0.737"],
  ["허리(폰)", "0.922", "0.899", "0.902"],
], [3360, 2000, 2000, 2000]));
children.push(Bul("★**in-domain CV 0.98은 낙관** — 새 손목 셋 실제 F1 0.74(정밀도 0.66, 헛알람 多). 허리는 0.90으로 견고. **주력기기(워치)가 더 약함** → L5 교차검증·미회복 net·네이티브 낙상 의존이 정당. '양 늘리면 일반화'는 오해(풀링은 in-domain만 부풀림)."));
children.push(P("고령 ADL 오탐 probe + 처방(피험자 분할, 누수 없음):", { bold: true }));
children.push(table(["손목 모델", "미지 고령 ADL 오탐율"], [
  ["젊은층만 학습(베이스라인)", "24.1% (4건 중 1건 헛알람)"],
  ["+ 고령 ADL 학습(처방)", "9.5% (−60%, 미지 고령자 일반화)"],
], [5360, 4000]));
children.push(Bul("★사용자 '데이터 더 모으자'의 정량 답: **표적 고령 ADL은 오탐 갭의 실제 답**(24→9.5%, 처음 보는 고령자에게도 일반화). 젊은 데이터만 쌓으면 이 24%는 안 보임."));
children.push(Bul("**그러나 양으로 못 사는 것**: ① 9.5%도 높아 L5 교차검증 필요 ② 고령 '낙상' recall 갭은 그대로(어떤 공개셋도 고령 진짜 낙상 없음). → 결론: 데이터 확장은 '실재하나 한정적'. 표적이면 유익, 무차별이면 검증연극. 실 갭은 POC(실 고령·실 낙상)."));
children.push(Bul("**처방 적용 완료 → §6-12 참조**: 종합 최적화 후 배포 손목모델 재학습(고령 ADL 포함)+위치별 임계. 재검증 무회귀 확인."));

children.push(H2("6-12. 낙상모델 종합 최적화 + 위치별 임계 (v0.14)"));
children.push(P("\"모든 경우의 수를 적용해 최선 도출\" — 위치별로 [데이터·고령ADL·증강] factorial을 LODO·고령FP·CV로 전부 비교(누수없음). 결론이 위치별로 정반대.", { italics: true }));
children.push(table(["손목 구성(LODO/고령FP)", "LODO F1", "고령 FP", "판정"], [
  ["C1 레거시(=구 배포)", "0.688", "0.415", "고령 오탐 41%"],
  ["C2 +SmartFallMM", "0.736", "0.240", "일반화↑"],
  ["C3 +고령ADL", "0.708", "0.095", "오탐 격감"],
  ["C4 +증강", "0.709", "0.109", "증강 효과 無"],
], [3360, 1600, 1600, 2800]));
children.push(Bul("**손목=재학습(C3)**: SmartFallMM가 일반화↑(0.69→0.74), 고령 ADL이 오탐 41.5%→9.5% 격감. 증강은 효과 없어 제외."));
children.push(Bul("**허리=유지(C1)**: ★레거시(SisFall+UMAFall)가 이미 LODO F1 0.949·고령FP 0.003로 최적 — SmartFallMM phone 추가가 오히려 악화(F1 0.90·FP 0.15). 폰은 몸중심이라 견고. '더 모으면 좋다'의 명백한 반례."));
children.push(P("위치별 임계 스윕 → 운영점(손목은 신호 거칠어 동일임계서 민감도 낮음 → 낮춤):", { bold: true }));
children.push(table(["위치", "임계", "민감도", "고령 FP", "vs 구 배포"], [
  ["손목(watch)", "0.40→0.30", "0.75→0.82", "0.42→0.15", "양축 압도(민감도↑·오탐↓)"],
  ["허리(phone)", "0.40 유지", "0.99", "0.003", "이미 최적"],
], [1900, 1500, 1600, 1560, 2800]));
children.push(Bul("**위치별 임계 구현**: config.FALL_PROBA_TH_BY_SOURCE={watch:0.30, phone:0.40}, FallDetector.proba_th(source별). 손목 0.30=민감도 0.82 회복+고령FP 0.15(구 배포 0.42 대비 63%↓), 둘 다 구 배포 압도."));
children.push(Bul("**재학습·검증**: 손목 4323윈도우(낙상1386, 피험자100, WEDA+UMAFall+SMM젊은+고령ADL) 학습→배포(구모델 .bak 백업). 피험자분할 CV sens 0.875. reverify 10/11 OK(F1 0.983 무회귀, R7 서빙검출 0.96·R8 오탐 0.03). 허리 미변경."));
children.push(Bul("**남은 한계(정직)**: 손목 고령 FP 9.5~15%도 여전히 L5 교차검증 의존 필요. 고령 '낙상' recall(R5 0.83)은 공개셋 부재로 미해결 — 이번 작업은 고령 '오탐' 축만 개선."));

children.push(H2("6-13. 손목 모델 강화 — 특징 공학 (v0.15)"));
children.push(P("손목 LODO 약점(F1 0.74)을 코드로 더 쥐어짜기. 2단계로 정직하게 탐색.", { italics: true }));
children.push(Bul("**1단계 분류기/정규화 — 실패**: ExtraTrees·HGB·보정·StandardScaler·RobustScaler 비교 → LODO F1 ≤+0.011(노이즈 수준). 정규화는 RF가 스케일불변이라 효과 0(확인). → 모델 선택은 데이터 한계."));
children.push(Bul("**2단계 특징 공학 — 성공**: 9개 추가특징(스펙트럼 1~3·3~8Hz 대역에너지, SMV 첨도·왜도, 피크 수, 사후정착비, 자기상관 피크, gyro-accel 상관 = 낙상 vs 손동작 변별). 손목 LODO F1 **0.713→0.744**(+0.031)·민감도 0.822→0.827·고령FP 0.151→0.135."));
children.push(table(["지표(손목 LODO)", "구 배포", "강화 후", "Δ"], [
  ["F1", "0.713", "0.744", "+0.031"],
  ["민감도", "0.822", "0.827", "+0.005"],
  ["고령 ADL 오탐", "0.151", "0.135", "−0.016"],
], [3360, 1800, 1800, 2400]));
children.push(Bul("**허리 무해 확인**: 추가특징이 허리도 LODO F1 0.949→0.951(중립~소폭↑) → 공용 extract_features 전역 통합 안전. base(0~13)+extra(14~22), 휴리스틱 폴백 인덱스 보존. 세 모델(손목·허리·기본폴백) 23특징 재학습."));
children.push(Bul("**재검증 9/11**(회귀 아님): 배포지표 전부↑(R7 서빙 0.96→0.97·R8 오탐 0.03→0.00·R5 고령recall 0.827→0.840). 2 ISSUE=고령recall 프로브(R5 standing·개선됐으나 미달, R11 고령가중은 배포 미사용 실험). 비용=FFT/자기상관(충격 시에만 추출→온디바이스 무관)."));

children.push(H2("6-14. POC 대안 — 파형-무관 캐스케이드(#2) + 네이티브 위임(#1) (v0.16)"));
children.push(P("고령 낙상 recall 갭은 데이터로 당장 못 풀음 → POC 없이 가능한 두 코드/아키텍처 완충.", { italics: true }));
children.push(Bul("**#2 파형-무관 캐스케이드**: 분류기가 고령 소프트폴(약점)을 놓쳐도, **센 충격(≥3.0g) + 8초 무활동**이면 분류기 proba와 무관하게 fall_long_lie 발화(L2.IMPACT_HARD_G, _candidate_hard). 물리로 분류기를 보완."));
children.push(table(["캐스케이드 검증(WEDA 손목)", "값", "의미"], [
  ["FP 자연지속(현실)", "0.000", "ADL 후 정상 움직이면 절대 오발 안 함"],
  ["FP 정지꼬리(최악)", "0.042", "부딪힌 뒤 실제 8초 정지하는 드문 경우(L5가 추가 차단)"],
  ["복구 효익", "측정불가", "WEDA 낙상=전부 '일어남' → '못 일어난 낙상' 데이터 없음"],
], [3360, 1500, 4500]));
children.push(Bul("→ 8초 무활동 게이트가 ADL 큰충격(손목 43%)을 **현실에선 완전히 차단**(FP 0). 효익=분류기 놓친 '못 일어난 고령 낙상'을 L3(3분) 아닌 **8초**에 포착 — 데이터 부재로 크기는 미측정이나 메커니즘·FP는 검증. 보험적 안전망."));
children.push(Bul("**#1 네이티브 위임(검증)**: 애플 CMFallDetectionManager·삼성 FALL_DETECTED는 *수백만 실제 낙상(고령 포함)* 학습 → 우리가 고령 낙상모델 만드는 대신 **그 이벤트를 받아 융합**(ingest_fall_event→fall_confirmed EMERGENCY+미회복 net 무장, 네이티브=주력·우리 모델=폴백). 119는 네이티브가 직접→우리는 guardian_push(가족). 통합(워치앱)만 남음."));
children.push(Bul("**정직**: #2 효익은 데이터 부재로 미측정(메커니즘만), #1은 통합 미완(워치앱·엔타이틀먼트). 둘 다 recall 갭의 '완충'이지 측정된 recall 개선 아님 — 근본은 FARSEEING/배포후 능동학습/POC. reverify 9/11(R8 서빙오탐 0 유지, 캐스케이드 무회귀)."));

children.push(H2("6-15. 능동 확인 루프(A) + 시스템 단위 recall(B) (v0.17)"));
children.push(P("질문 전환: 데이터 없이 '고령 낙상 파형 recall'은 못 올림 → 대신 '결국 가족이 위험을 아는가(시스템 recall)'를 올린다. 사람 응답을 정답으로.", { italics: true }));
children.push(Bul("**A 능동 확인 루프**: 충격+분류기 회색지대(proba [0.15, 발화임계)) → fall_suspected → **self_check**(워치 '괜찮으세요?', 가족 아님) → **45초 무응답 → no_response_fall 위급→guardian_push**. respond_ok() 시 해제. 분류기가 놓쳐도 '다친 사람은 응답 못 함'이 최종 신호. (config FALL_PROBA_SOFT, pipeline pending_check/respond_ok, l5 self_check 에스컬레이션)"));
children.push(P("B 시스템 단위 recall(held-out 분류기=비관적, WEDA낙상+사후 무활동+무응답):", { bold: true }));
children.push(table(["측정", "값", "의미"], [
  ["시스템 recall", "0.69", "분류기 단독(미탐多)을 방어층 합집합이 복구"],
  ["self-check가 잡음", "133/200", "압도적 — A 없으면 시스템 recall ≈0.03"],
  ["캐스케이드가 잡음", "5/200", "센충격+무활동"],
  ["중앙 지연", "45.9초", "self-check 무응답 타임아웃이 지배"],
], [2400, 1600, 5360]));
children.push(Bul("→ ★**A(self-check)가 고령 recall갭의 가장 큰 완충** — 분류기가 놓친 낙상 69%를 '무응답'으로 45초에 복구(데이터 0 필요, 사람이 정답). 잔여 31%=충격<2.5g+proba<0.15 **저충격 소프트폴**(모든 net 아래)."));
children.push(Bul("**UX 비용(정직)**: ADL의 16%가 self-check 프롬프트 유발. 단 '오경보' 아님(의식 있으면 응답→격상 0). recall(0.69) vs 프롬프트(16%)는 제품 튜닝(FALL_PROBA_SOFT 조절). 실 고령 일상은 격한 ADL 적어 실제 프롬프트율 더 낮음."));
children.push(Bul("**정직**: 시스템 recall(가족이 앎)은 '낙상 파형 recall'과 다른 지표 — 데이터 없이 달성 가능한 것으로 재정의. reverify 9/11(R8 서빙오탐 **0** 유지=self-check가 거짓 위급 안 만듦, 무회귀). 잔여 저충격 갭은 근본적으로 데이터(FARSEEING/능동학습)."));

children.push(H2("6-16. self-check 임계 검증 + 시스템 recall 정직화 (v0.18)"));
children.push(P("self-check 잔여 갭을 줄이려 FALL_PROBA_SOFT 최적화 시도 → 결론: 기존 0.15가 이미 knee(과적합 회피로 변경 안 함).", { italics: true }));
children.push(Bul("**LODO 임계 스윕(과적합 방지·3셋 평균)**: soft↓면 recall 약간↑·프롬프트 급증. 0.10→recall 0.966·고령프롬프트 18%, **0.15→0.957·9.2%(배포모델)**, 0.20→0.944·4.3%. 0.15가 균형점 — 낮추면 프롬프트 2배에 recall +0.9%p뿐."));
children.push(Bul("**배포모델 프롬프트율은 held-out보다 훨씬 낮음**(고령 ADL 학습 효과): 고령 ADL proba 중앙 0.04 → soft 0.15서 프롬프트 9.2%(허용). held-out 스윕(59%)은 비관적."));
children.push(Bul("**시스템 recall 정직화**: 스트리밍 0.69는 ①WEDA(손목 소프트폴=가장 어려운 셋) 특정값 ②회복-낙상 아티팩트. 못 일어난 시나리오(충격 절단+무활동)로 재측정 시 캐스케이드 66+self-check 72=138/200, L3 net(180s)은 고립검증 정상이나 앞의 둘이 먼저 잡음. **하드셋 0.69~3셋평균 0.96** 범위."));
children.push(Bul("**판단(과적합·오버엔지니어링 회피)**: 임계를 안 바꾸는 게 정답 — 분석이 기존 설계 검증. 잔여(저충격 손목 소프트폴, proba<0.15 AND 충격<2.5g)는 임계로 안전하게 못 잡음 = 데이터의 벽(FARSEEING/능동학습). 배포 코드 무변경."));

children.push(H2("6-17. 능동학습 데이터 엔진 — 배포가 곧 실데이터 수집 (v0.19)"));
children.push(P("데이터 영역의 현실적 해법: POC/FARSEEING 없이도 배포 자체로 실 고령 낙상 라벨을 모은다. self-check 응답이 곧 라벨.", { italics: true }));
children.push(Bul("**메커니즘**: 라벨 가치 있는 이벤트(fall_suspected/recovered/long_lie/confirmed/unrecovered) → 직전 10초 IMU 링버퍼 스냅샷 캡처(라벨 대기) → **사용자 '괜찮아요'(respond_ok)=오경보** · **가족 사후확인(confirm_incident)=낙상/오경보** → 디스크 적재(windows/*.npy + index.jsonl)."));
children.push(Bul("**루프 닫힘**: 수집 윈도우 → extract_window → extract_features(23특징) → train_fall_final 데이터에 append → 재학습. 즉 **배포가 오래 돌수록 실 고령 데이터가 쌓여 recall이 스스로 개선**(현재 약점을 데이터로 직접 공략)."));
children.push(Bul("**프라이버시**: collect_data(동의)·env WIDU_COLLECT=1 시에만 수집(기본 off). 저장은 IMU 신호+라벨+최소 메타(원좌표·식별자 없음). 코드(`widu/datalog.py`, pipeline capture/respond_ok/confirm_incident)."));
children.push(Bul("**서빙 API**: POST /users/<uid>/respond_ok · POST /users/<uid>/confirm_incident{is_fall} · GET /collector/stats. 가족 앱이 '낙상 맞나요?' 확인 → 라벨. 스모크: 캡처→라벨(가족/사용자)→적재→재로드(23특징) 전부 통과, 동의 off면 미수집."));
children.push(Bul("**의미**: 우리가 못 구하던 '실 고령 낙상'을 **배포 후 organic 수집**으로 확보하는 유일한 자력 경로. 수십 명 파일럿만으로 몇 달이면 실 라벨 누적 → POC/FARSEEING의 현실적 대안."));

children.push(H2("6-18. 원본(WIDYU-ai) vs WidU — 머리맞대 성능 검증 (v0.20)"));
children.push(P("원본 app.py 알고리즘(최근15 MA±2σ 밖 AND 고정band[≥100 or ≤80])을 그대로 재구현해 동일 입력으로 비교. scripts/benchmark_vs_baseline.py.", { italics: true }));
children.push(P("① 실데이터 오경보율 (PPG-DaLiA 건강 15명·35.9h, 건강=전부 오탐):", { bold: true }));
children.push(table(["시스템", "오경보/시간", "에피소드"], [
  ["WIDYU-ai(원본)", "54.6", "1,964 (하루 ~1,300건)"],
  ["WidU(L0+L1)", "0.5", "18 (≈110배 적음)"],
], [3360, 2500, 3500]));
children.push(P("② 응급 탐지/지연 (합성·안정시):", { bold: true }));
children.push(table(["응급", "원본 탐지/지연", "WidU 탐지/지연"], [
  ["급성 서맥(35)", "O / 0s", "O / 30s"],
  ["점진 서맥(70→35)", "O / 18s", "O / 292s"],
  ["급성 빈맥(160)", "O / 0s", "O / 30s"],
  ["점진 빈맥(70→160)", "O / 12s", "O / 230s"],
  ["안정 빈맥(135)", "O / 0s", "O / 30s"],
], [2860, 3250, 3250]));
children.push(Bul("**둘 다 응급은 다 탐지(무승부).** 단 원본의 '빠른 탐지'는 허상 — 점진 서맥을 18s에 잡은 건 HR이 아직 ~65(정상)일 때 발화한 것(≤80 band + 미세 outlier). ★**원본은 'HR 65 하락중(정상)'과 'HR 35(응급)'을 구별 못 함**(둘 다 result=1) = 고감도·저특이도 과발화. 이게 54.6 오경보/h와 같은 현상."));
children.push(Bul("**WidU는 둘을 분리**: L0(임상 하드바운드)=급성을 30s에 특이적으로, L1(개인화·맥락·3분지속)=미묘 이탈을 오탐 0.5/h로. 점진 케이스가 느린 건(230~292s) '실제 임상임계(<40/>150) 도달까지 대기' = HR 65를 응급이라 안 부르는 것."));
children.push(Bul("**원본 속도 우위는 무의미**: 55 오경보/h면 가족이 알림을 꺼버림(알람피로) → 실세계 응급 탐지율 사실상 0(양치기 소년). 보호자 신뢰=제품 생명인데 원본은 구조상 사용 불가."));
children.push(Bul("**+ 이건 전부 심박만의 비교** — 고령 응급 1위 **낙상**: 원본 0 탐지 vs WidU 허리 LODO F1 0.90·손목 0.74. 심박 무승부여도 낙상이 승부."));
children.push(Bul("**판정(데이터 근거)**: 응급 오경보 110배↓ + 커버리지(낙상·무활동·배회·추세) + 원본 유지/병행 이유 없음 → **WidU로 통째 교체 타당**. WidU 비용=점진 HR 몇 분 느림(급성은 L0 30s)·고령낙상 recall 0.84(능동학습 보완)."));

// ---- 7 ----
children.push(H1("7. 검증 데이터셋"));
children.push(table(["계층", "데이터셋", "접근/라이선스"], [
  ["L2 낙상", "SisFall · FallAllD · SmartFall", "개방 / IEEE DataPort 등록"],
  ["L1 HR×맥락", "PPG-DaLiA(CC BY 4.0) · WESAD", "UCI/Zenodo 개방"],
  ["L1 부정맥", "Pulsewatch", "PhysioNet"],
  ["L4 조기경보", "Stanford 웨어러블 · BIDMC · SHHS", "개방 / NSRR 등록"],
  ["생리 타당성", "VitalDB(API)", "개방, SCRUM-76 연장"],
], [1800, 4060, 3500]));

// ---- 8 ----
children.push(H1("8. 로드맵 (WIDYU 에픽 매핑)"));
children.push(Bul("**Now**: L0+L1(SCRUM-287 대체) + 지오펜스(SCRUM-49, 배포됨)."));
children.push(Bul("**Next**: L2 낙상(SCRUM-75 신규) — 최우선."));
children.push(Bul("**Then**: L3 무활동·배회 개인화."));
children.push(Bul("**Later(2026 2Q)**: L4 + VitalDB → Phase4 기저질환 조기진단."));

// ---- 9 ----
children.push(H1("9. 한계 · 리스크"));
children.push(Bul("**임상**: 미탐=책임. '선별·웰니스, 진단 아님' 고지 + 의료기관 연계(건국대 LINC 자문)."));
children.push(Bul("**법적**: 위치정보보호법(SCRUM-320 교육), 진단 주장 시 의료기기 규제 → Phase4 전 법률검토."));
children.push(Bul("**기술**: 배터리, 모션 아티팩트, 삼성↔애플 차이, 워치 측정중단(SCRUM-298)."));
children.push(Bul("**데이터**: L3 행동 라벨 공개셋 부재 → 합성+POC 의존. bpm 가공값만 오면 부정맥(RR) 제한적."));
children.push(Bul("**고령 낙상(개선됨)**: 손목 모델(WEDA)에서 소프트폴 recall **0.90**(허리 아티팩트 0.83 정정). 단 손목 **정밀도 0.73**(오탐)은 약점 → 미회복 net·폰 교차검증·POC로 보완. 단일 충격모델 과신 금지."));
children.push(Bul("**L1(심박) 오탐 — 해결됨(v0.10)**: 검증된 기법(긴 지속 300s+안정시에만)으로 PPG-DaLiA 오탐 2.06→0. 둔감 아님(6분 지속 잡음). 남은 확인: '0 오탐'의 sensitivity(미묘한 이상 미탐 여부)는 anomaly 라벨(POC)로 — 단 급성은 L0가 커버."));
children.push(Bul("**L3·L4 실데이터 검증 — 완료(v0.12)**: L4 안정심박 추세(Stanford 118명) 임상 크기서 탐지 0.82~0.97·헛경보 월~1회. L3 무활동(Stanford 119명)서 ★단독 12h 3.5/년 오발 적발→CAUTION 격하(D30). L3 지오펜스(GeoLife 48명) 이탈 0.82/일 등 임계 타당. 단 두 셋 모두 비고령(고령 특이성은 POC)."));
children.push(Bul("**일반화 현실 + 최적화(LODO, v0.13~14)**: 헤드라인 CV F1 0.98은 in-domain 낙관 — 미지 손목셋 실제 F1 0.74, 허리 0.90. 주력기기 워치가 약함 → 단독 신뢰 금지, L5 교차검증·네이티브 낙상 필수. **조치 적용**: 손목 재학습(C3)+임계 0.30 → 고령 ADL 오탐 41.5%→**15%**·민감도 0.75→**0.82**(구 배포 양축 압도). 허리는 유지(최적). 단 고령 FP 15%도 L5 의존, 고령 '낙상' recall은 공개셋 부재로 미해결(POC)."));
children.push(Bul("**미완 갭(정직)**: ① **실 낙상 부재** — SisFall·WEDA·UMAFall 모두 시뮬레이션 낙상(자원자), 실제 노쇠 고령자 진짜 낙상 아님. ② 손목 정밀도/오탐·통합·미회복 net 정밀도는 POC(금천에이스요양원)로만 확정. ③ **고령 코호트 부재** — L3/L4 검증셋도 일반 성인·젊은층, 고령 특이성·실 응급 라벨은 POC 필요. ④ Confluence 평문 비밀번호·법률(SCRUM-305) 미처리."));

// ---- 10 ----
children.push(H1("10. 의사결정 로그 (분기마다 갱신)"));
children.push(table(["일자", "버전", "변경/결정", "비고"], [
  [today, "v0.1", "5계층 파이프라인 + 데이터셋 로더 + 낙상 학습기 + Flask 서빙 초기 구축", "D1~D9 확정, 전 모듈 스모크 통과"],
  [today, "v0.2", "전처리·증강 재구축(안티앨리어싱·윈도우일치·누수없는 증강) + 워치/폰 이중 IMU 교차검증", "D10~D14. 11패스 자기재검증 11/11 통과. 회귀 무결."],
  [today, "v0.3", "실 SisFall 검증(F1 0.983 배포)·증강 efficacy A/B·VitalDB 복구·감사 버그 3건 교정", "D15~D17. 실데이터로 합성 1.0 폐기. 손목셋·PPG-DaLiA는 미완 갭."],
  [today, "v0.4", "10라운드 재검증 → ★고령 recall 0.83 적발(임계·가중 미해결)·임계 0.4 채택·인샘플누수 교정", "D18~D19. 10/11 OK(R5 ISSUE 추적). 고령=L3 안전망+실데이터 필요."],
  [today, "v0.5", "중간지평 '넘어진 뒤 미회복' 안전망(충격+3분 무활동→보호자) — 고령 처방. 3정공법 실측실패 진단.", "D20. 회수율 0.825·정밀도는 POC. 손목 자세불가→폰 IMU 길. 재검증 10/11 회귀무결."],
  [today, "v0.6", "오픈소스 WEDA-FALL(손목·고령) 확보 → 손목 검증(민감도 0.91·소프트폴 0.90) + 위치별 모델(워치=손목·폰=허리)", "D21~D22. '고령 0.83'=허리 아티팩트 정정. 허리→손목 40% 미탐 → 위치 분리 필수."],
  [today, "v0.7", "UMAFall로 cross-dataset 일반화 검증(민감도 전이됨 손목0.90·허리0.99) + 다중셋 결합 모델 배포(3셋·2위치)", "D23~D24. 단일셋 과적합 아님 확인. 정밀도는 기기별→결합학습·POC."],
  [today, "v0.8", "L1(심박) PPG-DaLiA 실검증 — 전제 검증·게이팅 절반오탐. ★FP 2.06/hr 과다=배포불가. + 네이티브 낙상 API 재정렬(워치 컴패니언)", "D25~D26. 주 신호 첫 실검증. 처방=워치 활동상태·네이티브 낙상. 재검증 10/11 무결."],
  [today, "v0.9", "기기 가용성 매트릭스 — 네이티브 낙상 입력+폰단독 폴백+워치/폰 교차검증. 둘 운용=정확도↑", "D27. 워치없으면 폰 자동전환. 스모크 3종 통과. 재검증 무결."],
  [today, "v0.10", "★L1 오탐 해결 — 웹 딥리서치(애플/ICU/Stanford) 검증기법(긴지속+안정시만) 적용 → 오탐 2.06→0", "D28. 둔감 아님(6분 지속 잡음). L0=급성·L1=소프트 분리. sensitivity는 POC."],
  [today, "v0.11", "L1 지속시간 최적화 — 스윕(PPG-DaLiA)으로 5분→3분(180s). 2분에 이미 오탐 0, 마진 두고 3분", "D29. 초기 5분은 과함(알림지연). 스모크 검증(3.5분 잡음·1분 무시). recall 1.0 유지."],
  [today, "v0.12", "★L3·L4 실데이터 검증(Stanford 웨어러블·GeoLife). L4 추세 임상크기 탐지 0.82~0.97·월~1회 오탐. ★L3 단독 무활동 3.5/년 오발 적발→CAUTION 격하", "D30. 마지막 미검증영역 종료. 지오펜스 카운팅버그·걸음결측 아티팩트 교정. 비고령=POC 갭. 재검증 무결."],
  [today, "v0.13", "데이터 표적확장(SmartFallMM) + LODO 일반화 검증 + 고령 처방. ★미지 손목 F1 0.74(CV 0.98 낙관)·허리 0.90. ★고령 ADL 오탐 24%→처방 9.5%", "D31. '데이터 더 모으자' 비판적 답=표적이면 유익(고령 오탐 60%↓)·무차별이면 검증연극. 고령 낙상 recall은 POC. 배포모델 무회귀."],
  [today, "v0.14", "낙상모델 종합 최적화(모든 구성 LODO/고령FP 비교) → ★손목 재학습(C3)+위치별임계(0.30): 고령FP 0.42→0.15·민감도 0.75→0.82(구배포 압도). ★허리 유지(SMM 추가가 악화)", "D32. 위치별 결론 정반대. 위치별 임계 config+FallDetector. 백업 .bak. reverify 10/11 OK(F1 0.983·R7 0.96·R8 0.03 무회귀). 고령 낙상 recall은 여전 POC."],
  [today, "v0.15", "손목 강화 — 특징공학 9개(스펙트럼·첨도·피크 등). 분류기/정규화는 실패(데이터한계)·특징은 성공: 손목 LODO F1 0.713→0.744·고령FP 0.151→0.135, 허리 무해", "D33. 공용 extract_features 23특징·3모델 재학습(기본폴백 14→23 누락 적발·교정). reverify 9/11(회귀 아님: 배포지표 전부↑ R7 0.97·R8 0.00·R5 고령recall 0.84; ISSUE 2개=고령recall 프로브)."],
  [today, "v0.16", "POC 대안 둘 — #2 파형-무관 캐스케이드(센충격≥3.0g+8초무활동→분류기무관 fall_long_lie, 현실FP 0·최악 4.2%) + #1 네이티브 위임(검증). 고령 recall갭 완충", "D34. #2 효익은 데이터부재로 미측정(WEDA낙상=일어남). #1 통합 미완(워치앱). 둘 다 insurance. reverify 9/11(R8 0 유지·무회귀)."],
  [today, "v0.17", "능동 확인 루프(A)+시스템 recall(B) — 지표 재정의. A=회색지대→self_check→45초무응답→격상. B=held-out 시스템 recall 0.69(self-check가 133/200 복구, A없으면 0.03), 중앙지연 46초", "D35. 사람 응답=정답(데이터 0). UX=ADL 16% 프롬프트(오경보 아님, 응답시 해제). 잔여=저충격 소프트폴. reverify 9/11(R8 0 유지)."],
  [today, "v0.18", "self-check 임계 검증(LODO 스윕 3셋평균) → 0.15가 이미 knee(배포 프롬프트 9.2%·recall 0.957), 변경 안 함=과적합 회피. 시스템 recall 정직화(하드셋 0.69~평균 0.96)", "D36. 분석이 기존 설계 검증·억지 튜닝 거부. L3 net 고립검증 정상. 잔여=저충격 손목 소프트폴=데이터 벽. 배포 코드 무변경(reverify 불필요)."],
  [today, "v0.19", "능동학습 데이터 엔진 — 배포=실데이터 수집. 이벤트→10초 IMU 캡처→사용자/가족 응답이 라벨→디스크 적재→재학습 루프. 동의 게이트(기본 off). datalog.py + serving 3엔드포인트", "D37. self-check를 라벨 수집기로 확장. POC/FARSEEING 없이 실 고령 낙상 확보하는 자력 경로. 스모크 통과(캡처/라벨/적재/재로드/동의off). 수집 비활성시 동작 불변(reverify 무회귀)."],
  [today, "v0.20", "원본(WIDYU-ai) vs WidU 머리맞대 성능검증. 오경보 54.6 vs 0.5/h(110배↓)·응급탐지 무승부(원본은 과발화로 잡음)·낙상 원본 0. → 통째 교체 타당", "D38. benchmark_vs_baseline.py(원본 app.py 재구현·동일입력). 원본 속도우위는 알람피로로 무의미(실 recall≈0). 보호자 신뢰·커버리지 WidU 압승."],
], [1300, 900, 5160, 2000]));
children.push(P(""));
children.push(P("(다음 분기 예시: 실 SisFall 학습 결과, L1 개인화 PPG-DaLiA 검증, POC 라벨링 프로토콜 확정 등 추가)", { italics: true, color: "777777" }));

const doc = new Document({
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 30, bold: true, font: FONT, color: BLUE },
        paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 25, bold: true, font: FONT },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [ { reference: "b", levels: [
    { level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 520, hanging: 260 } } } } ] } ] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun("WidU 해설문서 v0.10 · "), new TextRun({ children: [PageNumber.CURRENT] })] })] }) },
    children,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(__dirname, "WidU_해설문서.docx");
  fs.writeFileSync(out, buf);
  console.log("WROTE " + out + " (" + buf.length + " bytes)");
});
