"""캐스케이드(분류기-독립 hard-impact 경로) 스트리밍 검증 — 비용 vs 효익.

(1) FP(비용): 배포 손목모델로 실 WEDA ADL을 스트리밍 + 무활동 꼬리(최악조건) →
    fall_long_lie 오발율. 무활동 게이트가 ADL 큰충격(43%)을 거르는지.
(2) 복구(효익): WEDA '제외' 학습 손목모델로 WEDA 낙상 스트리밍 + 무활동 꼬리 →
    fall_long_lie 발화 중 impact_driven=False(분류기단독) vs True(캐스케이드 복구).
    한 번의 패스로 분류기-단독 recall과 캐스케이드 recall을 동시 측정.
산출 → artifacts/cascade_stream_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import RandomForestClassifier

from widu.config import L2
from widu.types import IMUSample, AlertLevel
from widu.l2_fall import FallDetector, FallModel, extract_features
from widu.preprocess import resample_antialiased, extract_window
from widu.datasets import weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)


class _InlineModel:
    """학습된 clf 를 FallModel 인터페이스로 감싼다(held-out 모델 주입용)."""
    def __init__(self, clf): self.model = clf; self.trained = True
    def fall_proba(self, feat): return float(self.model.predict_proba(feat.reshape(1, -1))[0, 1])


def stream_trial(arr, model, immobile_tail_s=12.0):
    """trial(50Hz, N×6) 스트리밍 + 무활동 꼬리 → (fired, impact_driven)."""
    fd = FallDetector(source="watch", model=model)
    t = 0.0; dt = 1.0 / L2.FS
    fired = None
    for row in arr:
        d = fd.update(IMUSample(t, row[0], row[1], row[2], row[3], row[4], row[5])); t += dt
        if d is not None and d.scenario == "fall_long_lie":
            fired = d
    # 무활동 꼬리(거의 정지: 중력만 + 미세잡음)
    rng = np.random.default_rng(0)
    for _ in range(int(immobile_tail_s * L2.FS)):
        n = rng.normal(0, 0.01, 3)
        d = fd.update(IMUSample(t, n[0], n[1], 1.0 + n[2], 0.0, 0.0, 0.0)); t += dt
        if d is not None and d.scenario == "fall_long_lie":
            fired = d
    if fired is None:
        return False, False
    return True, bool(fired.evidence.get("impact_driven", False))


def eval_fp(model):
    fp = 0; n = 0
    for arr, lab, subj, ft in weda.iter_dataset(DATA / "WEDA_raw"):
        if lab != 0:
            continue
        win = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < MIN_WIN:
            continue
        n += 1
        fired, _ = stream_trial(arr, model)
        if fired:
            fp += 1
    return {"n_adl": n, "false_fire": fp, "fp_rate_worstcase": round(fp / max(n, 1), 3)}


def build_heldout_wo_weda():
    """WEDA 제외(UMAFall-wrist + SMM young watch + 고령ADL) 손목모델."""
    X, y = [], []
    def add(gen, fs, only_adl=False):
        for arr, lab, subj, *_ in gen:
            if lab < 0 or (only_adl and lab != 0):
                continue
            a = arr if fs == L2.FS else resample_antialiased(arr, fs, L2.FS)
            w = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
            if len(w) >= MIN_WIN:
                X.append(extract_features(np.asarray(w, float), L2.FS)); y.append(int(lab))
    add(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS)
    add(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS)
    add(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS, only_adl=True)
    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0, n_jobs=-1)
    clf.fit(np.array(X), np.array(y))
    return _InlineModel(clf)


def eval_recall_recovery(heldout):
    clf_only = casc = n = 0
    for arr, lab, subj, ft in weda.iter_dataset(DATA / "WEDA_raw"):
        if lab != 1:
            continue
        win = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < MIN_WIN:
            continue
        n += 1
        fired, impact_driven = stream_trial(arr, heldout)
        if fired:
            casc += 1
            if not impact_driven:
                clf_only += 1
    return {"n_fall": n, "clf_only_recall": round(clf_only / max(n, 1), 3),
            "cascade_recall": round(casc / max(n, 1), 3),
            "recovered_by_cascade": round((casc - clf_only) / max(n, 1), 3)}


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("=== (1) FP(비용): 배포모델·실 ADL + 무활동 꼬리(최악) ===", flush=True)
    fp = eval_fp(FallModel(L2.MODEL_PATH_WRIST))
    print(json.dumps(fp, ensure_ascii=False, indent=2))
    print("\n=== (2) 복구(효익): WEDA-제외 모델로 WEDA 낙상 ===", flush=True)
    heldout = build_heldout_wo_weda()
    rec = eval_recall_recovery(heldout)
    print(json.dumps(rec, ensure_ascii=False, indent=2))
    report = {"impact_hard_g": L2.IMPACT_HARD_G, "fp_cost": fp, "recall_benefit": rec}
    (ROOT / "artifacts" / "cascade_stream_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[saved] artifacts/cascade_stream_report.json")


if __name__ == "__main__":
    main()
