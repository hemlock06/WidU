"""종합 검증 하니스 — 각 계층 + 융합을 실제로 돌려 지표 산출.

데이터:
  - HR 이상: 합성 스트림에 이상 주입(공개셋은 라벨 부재 → 합성+POC로 보완하는 설계).
  - 낙상: 학습 모델 + 합성/실 SisFall 윈도우.
결과 → artifacts/validation_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.pipeline import StreamProcessor
from widu.types import AlertLevel
from widu.l2_fall import FallModel, extract_features
from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.datasets import synthetic, sisfall
from widu.eval.metrics import binary_metrics


def validate_hr() -> dict:
    """정상 구간 + 주입된 빈맥/서맥 이벤트에 대한 탐지율·오경보(에피소드 단위)."""
    from widu.types import HRSample, IMUSample, Accuracy
    sp = StreamProcessor()
    u = "val"
    # 새 L1: 안정맥락(rest) + 긴 지속(300s) 필요 → 이벤트를 6분으로, 안정 IMU 동반.
    # 600~960 지속 안정빈맥 120(L1), 1320~1680 서맥 38(L0). HR 2초 간격.
    plan = [(0, 600, None), (600, 960, 120), (960, 1320, None),
            (1320, 1680, 38), (1680, 1980, None)]
    events = [(600, 960), (1320, 1680)]
    grace = 120
    levels = {}
    sec = 0
    rng = np.random.default_rng(0)
    for (s, e, bpm) in plan:
        for t in range(s, e, 2):                 # HR 2초 간격
            for k in range(6):                   # 안정 IMU 동반 → context=REST
                sp.ingest_imu(u, IMUSample(t + k * 0.04, 0.0, 0.0, 1.0))
            val = (72 + 5 * np.sin(2 * np.pi * t / 1980) + rng.normal(0, 2.0)) if bpm is None else bpm + rng.normal(0, 1.5)
            a = sp.ingest_hr(u, HRSample(float(t), float(max(25, val)), Accuracy.HIGH))
            levels[t] = a.level in (AlertLevel.CAUTION, AlertLevel.EMERGENCY)
            sec = t

    # 에피소드(상승 에지) 추출
    episodes = []
    prev = False
    for t in sorted(levels):
        cur = levels[t]
        if cur and not prev:
            episodes.append(t)
        prev = cur

    def near_event(tt):
        return any(s <= tt <= e + grace for (s, e) in events)
    detected = sum(1 for (s, e) in events
                   if any(s - 5 <= ep <= e + grace for ep in episodes))
    false_eps = [ep for ep in episodes if not near_event(ep)]
    days = (sec + 1) / 86400.0
    return {
        "events_total": len(events),
        "events_detected": detected,
        "event_recall": round(detected / len(events), 3),
        "alert_episodes": len(episodes),
        "false_episodes": len(false_eps),
        "false_alarms_per_user_day": round(len(false_eps) / days, 2),
    }


def validate_fall() -> dict:
    """학습 모델로 낙상/ADL 윈도우 분류 + 스트리밍 end-to-end."""
    model = FallModel()
    root = ROOT / "data" / "SisFall"
    X, y = [], []
    if root.exists() and any(root.rglob("*.txt")):
        src = "SisFall"
        for arr, lab, _ in sisfall.iter_dataset(root):
            arr = resample_antialiased(arr, sisfall.FS, L2.FS)   # 학습과 동일 전처리
            win = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
            if len(win) < int(L2.WIN_SEC * L2.FS * 0.5):
                continue
            X.append(extract_features(win, L2.FS)); y.append(lab)
    else:
        src = "synthetic"
        for i in range(150):
            X.append(extract_features(synthetic.fall_window(seed=5000+i))); y.append(1)
            X.append(extract_features(synthetic.adl_window(seed=9000+i))); y.append(0)
    X = np.array(X); y = np.array(y)
    pred = (np.array([model.fall_proba(f) for f in X]) >= 0.5).astype(int)
    m = binary_metrics(y, pred)   # ⚠ 인샘플(배포 모델이 학습데이터를 평가) — 일반화 아님

    # 스트리밍 end-to-end (1건)
    sp = StreamProcessor()
    fired = None
    for s in synthetic.imu_fall_sequence(seed=1):
        o = sp.ingest_imu("f1", s)
        if o and o.level == AlertLevel.EMERGENCY:
            fired = o.reason_ko

    result = {
        "source": src, "n": int(len(y)),
        "model_trained": model.trained,
        # 인샘플 적합도(≈1.0 정상): 모델 적재·전처리 일치 sanity. 일반화 수치 아님.
        "in_sample_sanity": m.summary(),
        "note": "in_sample=학습데이터 평가(누수). 일반화는 피험자분할 CV(아래)를 볼 것.",
        "stream_emergency": fired,
    }
    # 진짜 일반화 수치: 피험자분할 CV (eval_augmentation.py 산출물)
    cv = ROOT / "artifacts" / "augmentation_efficacy.json"
    if cv.exists():
        c = json.loads(cv.read_text(encoding="utf-8"))
        result["subject_split_cv"] = c.get("with_aug")
        result["cv_no_aug"] = c.get("no_aug")
    return result


def main():
    report = {
        "hr_anomaly": validate_hr(),
        "fall": validate_fall(),
    }
    out = ROOT / "artifacts" / "validation_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
