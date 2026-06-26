"""Cross-dataset 일반화 — 우리 모델이 다른 기기/인구에서도 유지되나.

지금까지: 손목=WEDA만, 허리=SisFall만 (각 단일셋). 단일셋 과적합이면 헤드라인 0.91이 허상.
측정:
  [손목] UMAFall-wrist 자체 CV(상한) vs WEDA모델→UMAFall-wrist(전이)
  [허리] UMAFall-waist 자체 CV(상한) vs SisFall모델→UMAFall-waist(전이)
전이 - 자체CV 하락폭 = 일반화 갭. (UMAFall 20Hz→50Hz 업샘플이라 rate도 갭에 포함)
결과 → artifacts/crossdataset.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.datasets import umafall
from widu.preprocess import extract_window
from widu.l2_fall import extract_features, FallModel
from widu.augment import augment_train
from widu.eval.metrics import binary_metrics

TH = L2.FALL_PROBA_TH


def feats(ws):
    return np.array([extract_features(np.asarray(w, float), L2.FS) for w in ws])


def load_uma(position):
    root = ROOT / "data" / "UMAFall_raw"
    W, Y, S = [], [], []
    for arr, lab, subj, age in umafall.iter_dataset(root, position=position):
        w = extract_window(arr, L2.FS, L2.WIN_SEC, 0.75)
        if len(w) < int(L2.WIN_SEC * L2.FS * 0.5):
            continue
        W.append(w); Y.append(lab); S.append(subj)
    return W, np.array(Y), np.array(S)


def within_cv(W, Y, S):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    oof = np.full(len(Y), np.nan)
    for tr, te in GroupKFold(min(5, len(set(S)))).split(np.arange(len(Y)), Y, S):
        Wtr, Ytr, _ = augment_train([W[i] for i in tr], Y[tr], S[tr], n_aug=2, seed=0)
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1).fit(feats(Wtr), Ytr)
        oof[te] = clf.predict_proba(feats([W[i] for i in te]))[:, 1]
    m = binary_metrics(Y, (oof >= TH).astype(int))
    return {"sensitivity": round(m.sensitivity, 3), "precision": round(m.precision, 3),
            "f1": round(m.f1, 3)}


def transfer(model_path, W, Y):
    m = FallModel(model_path)
    if not m.trained:
        return {"note": "모델 없음"}
    X = feats(W)
    pred = (np.array([m.fall_proba(f) for f in X]) >= TH).astype(int)
    r = binary_metrics(Y, pred)
    return {"sensitivity": round(r.sensitivity, 3), "precision": round(r.precision, 3),
            "f1": round(r.f1, 3)}


def main():
    if not (ROOT / "data" / "UMAFall_raw").exists():
        print("UMAFall 미발견."); return
    t0 = time.time()
    Ww, Yw, Sw = load_uma("WRIST")
    Wa, Ya, Sa = load_uma("WAIST")
    print(f"UMAFall 손목 {len(Yw)}윈도우(낙상 {sum(Yw)}), 허리 {len(Ya)}윈도우(낙상 {sum(Ya)}) {time.time()-t0:.0f}s")

    report = {
        "wrist": {
            "umafall_within_cv": within_cv(Ww, Yw, Sw),
            "WEDA_model_transfer": transfer(L2.MODEL_PATH_WRIST, Ww, Yw),
        },
        "waist": {
            "umafall_within_cv": within_cv(Wa, Ya, Sa),
            "SisFall_model_transfer": transfer(L2.MODEL_PATH_WAIST, Wa, Ya),
        },
        "n_wrist": int(len(Yw)), "n_waist": int(len(Ya)),
        "note": "UMAFall 20Hz→50Hz 업샘플 → 전이 갭에 device+population+rate 혼재(실배포 일반화).",
    }
    (ROOT / "artifacts" / "crossdataset.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # 갭 요약
    for pos, mkey in [("wrist", "WEDA_model_transfer"), ("waist", "SisFall_model_transfer")]:
        w = report[pos]["umafall_within_cv"]["sensitivity"]
        t = report[pos][mkey]["sensitivity"]
        print(f"[{pos}] 자체CV 민감도 {w} → 전이 {t}  (갭 {round(w-t,3)})")


if __name__ == "__main__":
    main()
