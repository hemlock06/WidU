"""시스템 단위 recall — '낙상을 8초에 분류했나'가 아니라 '결국 가족이 알았나'.

분류기가 못 맞혀도(held-out 모델=WEDA 미학습 → 일부 미탐) 사후 무활동+무응답이면
방어층 합집합이 잡는지 측정: 캐스케이드(센충격+8s) · self-check(45s 무응답) ·
L3 미회복(충격+3분) · 분류기(proba≥th). 어느 층이 며칠/몇초에 잡는지 + 시스템 recall.

데이터: WEDA 낙상(실 충격) + 사후 무활동 꼬리 주입('넘어져 못 일어남', 응답 없음).
산출 → artifacts/system_recall_report.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import RandomForestClassifier

from widu.config import L2
from widu.types import IMUSample, AlertLevel
from widu.l2_fall import extract_features, FallModel
from widu.preprocess import resample_antialiased, extract_window
from widu.pipeline import StreamProcessor
from widu.datasets import weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)
TAIL_S = 200.0           # 사후 무활동(못 일어남) 관찰 — L3 3분 net 포함
MAX_FALLS = 200          # 런타임 위해 표본


class _M:
    def __init__(self, clf): self.model = clf; self.trained = True
    def fall_proba(self, f): return float(self.model.predict_proba(f.reshape(1, -1))[0, 1])


def heldout_wo_weda():
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
    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                 random_state=0, n_jobs=-1).fit(np.array(X), np.array(y))
    return _M(clf)


def simulate(arr, model, respond=False):
    """trial + 무활동 꼬리(무응답) 스트리밍 → (first_emergency_scenario, latency_s)."""
    sp = StreamProcessor(shared_fall_model=model)
    u = "s"; t = 0.0; dt = 1.0 / L2.FS
    # 워밍업(맥락 안정)
    for _ in range(100):
        sp.ingest_imu(u, IMUSample(t, 0.0, 0.0, 1.0)); t += dt
    t0 = t
    # ★'못 일어난 낙상' 시나리오: 충격 직후 절단(회복 동작 제거) → 무활동.
    #   (WEDA 원본은 넘어졌다 일어남 → 회복 동작이 L3 미회복 무장을 해제 = 과소평가 아티팩트)
    from widu.l2_fall import _smv as _smvf
    smv = _smvf(np.asarray(arr, float)[:, :3])
    peak = int(np.argmax(smv))
    cut = min(len(arr), peak + int(0.5 * L2.FS))   # 충격 + 0.5s 까지만
    for row in arr[:cut]:
        sp.ingest_imu(u, IMUSample(t, row[0], row[1], row[2], row[3], row[4], row[5])); t += dt
    impact_end = t
    rng = np.random.default_rng(0)
    first = None
    n_tail = int(TAIL_S * L2.FS)
    for i in range(n_tail):
        n = rng.normal(0, 0.01, 3)
        a = sp.ingest_imu(u, IMUSample(t, n[0], n[1], 1.0 + n[2], 0.0, 0.0, 0.0)); t += dt
        if respond and (t - impact_end) > 5:      # (옵션) 5초 후 사용자 응답
            sp.respond_ok(u, t)
        if first is None and a is not None and a.level == AlertLevel.EMERGENCY:
            sc = max(a.detections, key=lambda d: d.level.rank).scenario
            first = (sc, round(t - impact_end, 1))
    return first


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("held-out(WEDA 제외) 모델 학습...", flush=True)
    model = heldout_wo_weda()
    falls = [arr for arr, lab, subj, ft in weda.iter_dataset(DATA / "WEDA_raw")
             if lab == 1 and len(extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)) >= MIN_WIN]
    falls = falls[:MAX_FALLS]
    print(f"낙상 {len(falls)}건 시뮬(사후 무활동 {TAIL_S:.0f}s·무응답)\n", flush=True)
    caught = 0; mech = Counter(); lats = []
    for i, arr in enumerate(falls):
        res = simulate(arr, model)
        if res is not None:
            caught += 1; mech[res[0]] += 1; lats.append(res[1])
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(falls)} 처리...", flush=True)
    lats = np.array(lats) if lats else np.array([0.0])
    report = {
        "n_falls": len(falls), "tail_s": TAIL_S,
        "system_recall": round(caught / len(falls), 3),
        "caught_by_mechanism": dict(mech),
        "latency_s": {"median": round(float(np.median(lats)), 1),
                      "p90": round(float(np.percentile(lats, 90)), 1),
                      "max": round(float(lats.max()), 1)},
        "note": "held-out 모델(WEDA 미학습) → 분류기 단독은 일부 미탐. 시스템 recall=방어층 합집합. "
                "self_check/no_response_fall·fall_long_lie(impact_driven)·fall_unrecovered = 비분류기 복구.",
    }
    print("\n=== 시스템 단위 recall(방어층 합집합) ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (ROOT / "artifacts" / "system_recall_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
