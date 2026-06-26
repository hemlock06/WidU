"""손목 낙상모델 강화 — 데이터 고정(C3), 모델/정규화 변형을 LODO로 정직 비교.

손목 LODO F1 0.71~0.74가 약점(교차기기 일반화). 특징은 한 번만 추출(캐시),
분류기·정규화·하이퍼파라미터만 바꿔 LODO F1 + 고령 FP(@th 0.30) 비교.
'강화'를 주장하려면 LODO(미지 출처)에서 올라야 함 — in-domain 부풀림 금지.

변형:
  M0 RF-300            (현 배포 baseline)
  M1 RF-reg            (min_samples_leaf=4, max_features=sqrt — 과적합 억제)
  M2 ExtraTrees-400
  M3 HistGradientBoost
  M4 RF + isotonic 보정 (CalibratedClassifierCV)
  M5 RF-300 + 표준화    (StandardScaler — 교차기기 스케일 차 완화)
  M6 RF-300 + 로버스트  (RobustScaler — 이상치/기기차 강건)
산출 → artifacts/wrist_strengthen_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import (RandomForestClassifier, ExtraTreesClassifier,
                              HistGradientBoostingClassifier)
from sklearn.calibration import CalibratedClassifierCV
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features
from widu.eval.metrics import binary_metrics
from widu.datasets import weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)
TH = L2.FALL_PROBA_TH_BY_SOURCE["watch"]   # 0.30


def cache_feats(gen, src_fs, only_adl=False):
    X, y, g = [], [], []
    for arr, lab, subj, *_ in gen:
        if lab < 0 or len(arr) < 4 or (only_adl and lab != 0):
            continue
        a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
        w = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(w) >= MIN_WIN:
            X.append(extract_features(np.asarray(w, float), L2.FS)); y.append(int(lab)); g.append(subj)
    return np.array(X), np.array(y), np.array(g)


def model(name):
    if name == "M0_RF300":
        return RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0, n_jobs=-1)
    if name == "M1_RF_reg":
        return RandomForestClassifier(n_estimators=400, min_samples_leaf=4, max_features="sqrt",
                                      class_weight="balanced", random_state=0, n_jobs=-1)
    if name == "M2_ExtraTrees":
        return ExtraTreesClassifier(n_estimators=400, class_weight="balanced", random_state=0, n_jobs=-1)
    if name == "M3_HGB":
        return HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05,
                                              l2_regularization=1.0, random_state=0)
    if name == "M4_RF_calib":
        base = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0, n_jobs=-1)
        return CalibratedClassifierCV(base, method="isotonic", cv=3)
    if name == "M5_RF_std":
        return make_pipeline(StandardScaler(),
                             RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                                    random_state=0, n_jobs=-1))
    if name == "M6_RF_robust":
        return make_pipeline(RobustScaler(),
                             RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                                    random_state=0, n_jobs=-1))
    raise ValueError(name)


def evaluate(name, sources, elderly):
    names = list(sources)
    # LODO
    s, p, f = [], [], []
    for held in names:
        Xtr = np.vstack([sources[n][0] for n in names if n != held] + [elderly[0]])
        ytr = np.concatenate([sources[n][1] for n in names if n != held] + [np.zeros(len(elderly[0]), int)])
        clf = model(name).fit(Xtr, ytr)
        Xte, yte = sources[held][0], sources[held][1]
        pr = clf.predict_proba(Xte)[:, 1]
        m = binary_metrics(yte, (pr >= TH).astype(int)).summary()
        s.append(m["sensitivity"]); p.append(m["precision"]); f.append(m["f1"])
    # 고령 FP (피험자 분할)
    yw = np.vstack([sources[n][0] for n in names]); yy = np.concatenate([sources[n][1] for n in names])
    Xo, go = elderly[0], elderly[1]
    fps = []
    for tr, te in GroupKFold(5).split(Xo, np.zeros(len(Xo)), go):
        Xtr = np.vstack([yw, Xo[tr]]); ytr = np.concatenate([yy, np.zeros(len(tr), int)])
        clf = model(name).fit(Xtr, ytr)
        fps.append(float((clf.predict_proba(Xo[te])[:, 1] >= TH).mean()))
    return {"lodo_sens": round(np.mean(s), 3), "lodo_prec": round(np.mean(p), 3),
            "lodo_f1": round(np.mean(f), 3), "elderly_fp": round(float(np.mean(fps)), 3)}


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("특징 추출(1회 캐시)...", flush=True)
    sources = {
        "WEDA": cache_feats(weda.iter_dataset(DATA / "WEDA_raw"), weda.FS),
        "UMAFall": cache_feats(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS),
        "SmartFallMM": cache_feats(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS),
    }
    Xo, yo, go = cache_feats(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS)
    elderly = (Xo[yo == 0], go[yo == 0])
    for n in sources:
        print(f"  {n}: {len(sources[n][1])} (낙상 {int(sources[n][1].sum())})", flush=True)
    print(f"  고령ADL: {len(elderly[0])} | th={TH}\n", flush=True)

    variants = ["M0_RF300", "M1_RF_reg", "M2_ExtraTrees", "M3_HGB",
                "M4_RF_calib", "M5_RF_std", "M6_RF_robust"]
    report = {}
    for v in variants:
        r = evaluate(v, sources, elderly)
        report[v] = r
        flag = "  ← baseline" if v == "M0_RF300" else ""
        print(f"  {v:16s} LODO F1={r['lodo_f1']:.3f} sens={r['lodo_sens']:.3f} "
              f"prec={r['lodo_prec']:.3f} | 고령FP={r['elderly_fp']:.3f}{flag}", flush=True)

    base = report["M0_RF300"]["lodo_f1"]
    best = max(report, key=lambda k: (report[k]["lodo_f1"], -report[k]["elderly_fp"]))
    print(f"\n최고 LODO F1: {best} ({report[best]['lodo_f1']:.3f} vs baseline {base:.3f}, "
          f"Δ{report[best]['lodo_f1']-base:+.3f})")
    report["_summary"] = {"baseline_f1": base, "best": best,
                          "best_f1": report[best]["lodo_f1"],
                          "delta": round(report[best]["lodo_f1"] - base, 3)}
    (ROOT / "artifacts" / "wrist_strengthen_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[saved] artifacts/wrist_strengthen_report.json")


if __name__ == "__main__":
    main()
