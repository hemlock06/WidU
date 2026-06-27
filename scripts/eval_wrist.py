"""손목(우리 실제 기기) 낙상 검증 — WEDA-FALL(손목·고령·50Hz).

지금까지는 SisFall=허리(폰 대용)뿐 → 손목 미검증이 핵심 한계였음.
WEDA로 실측:
  A) 손목 자체 CV: 우리 기기 분포에서의 진짜 낙상/고령/소프트폴 recall.
  B) 일반화 갭: 허리(SisFall) 학습모델 → 손목(WEDA) 적용 시 성능 저하.
결과 → artifacts/wrist_eval.json
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
from widu.falleval import feats  # 공유 헬퍼(DRY)
from widu.datasets import weda, sisfall
from widu.preprocess import extract_window, resample_antialiased
from widu.l2_fall import FallModel
from widu.augment import augment_train
from widu.eval.metrics import binary_metrics

TH = L2.FALL_PROBA_TH




def load_weda():
    root = ROOT / "data" / "WEDA_raw"
    W, Y, S, FT = [], [], [], []
    t0 = time.time()
    for arr, lab, subj, ft in weda.iter_dataset(root):
        w = extract_window(arr, L2.FS, L2.WIN_SEC, 0.75)
        if len(w) < int(L2.WIN_SEC * L2.FS * 0.5):
            continue
        W.append(w); Y.append(lab); S.append(subj); FT.append(ft)
    print(f"WEDA 손목 {len(Y)}윈도우 (낙상 {sum(Y)}, ADL {len(Y)-sum(Y)}, 피험자 {len(set(S))}) {time.time()-t0:.0f}s")
    return W, np.array(Y), np.array(S), np.array(FT)


def wrist_cv(W, Y, S, FT):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    oof = np.full(len(Y), np.nan)
    for tr, te in GroupKFold(5).split(np.arange(len(Y)), Y, S):
        Wtr, Ytr, _ = augment_train([W[i] for i in tr], Y[tr], S[tr], n_aug=2, seed=0)
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1).fit(feats(Wtr), Ytr)
        oof[te] = clf.predict_proba(feats([W[i] for i in te]))[:, 1]
    pred = (oof >= TH).astype(int)
    m = binary_metrics(Y, pred)
    soft = np.isin(FT, list(weda.SOFT_FALL_TYPES)) & (Y == 1)
    hard = (~np.isin(FT, list(weda.SOFT_FALL_TYPES))) & (Y == 1)
    return {
        "f1": round(m.f1, 3), "sensitivity": round(m.sensitivity, 3),
        "specificity": round(m.specificity, 3), "precision": round(m.precision, 3),
        "soft_fall_recall_F05_08": round(float((pred[soft] == 1).mean()), 3),
        "hard_fall_recall": round(float((pred[hard] == 1).mean()), 3),
        "n_soft": int(soft.sum()), "n_hard": int(hard.sum()),
    }


def cross_waist_to_wrist(Wwrist, Ywrist):
    """허리(SisFall) 학습 배포모델 → 손목(WEDA) 적용. 일반화 갭."""
    model = FallModel()
    if not model.trained:
        return {"note": "SisFall 모델 없음"}
    X = feats(Wwrist)
    pred = (np.array([model.fall_proba(f) for f in X]) >= TH).astype(int)
    m = binary_metrics(Ywrist, pred)
    return {"sensitivity": round(m.sensitivity, 3), "precision": round(m.precision, 3),
            "f1": round(m.f1, 3),
            "note": "허리 학습 → 손목 적용. 손목 CV 대비 하락폭이 도메인 갭."}


def main():
    if not (ROOT / "data" / "WEDA_raw").exists():
        print("WEDA 미발견."); return
    W, Y, S, FT = load_weda()
    print("[A] 손목 자체 CV (우리 기기 분포)...")
    a = wrist_cv(W, Y, S, FT)
    print("   ", a)
    print("[B] 허리→손목 일반화 갭...")
    b = cross_waist_to_wrist(W, Y)
    print("   ", b)
    report = {"wrist_self_cv": a, "waist_to_wrist_transfer": b,
              "n_windows": int(len(Y)), "n_subjects": int(len(set(S)))}
    (ROOT / "artifacts" / "wrist_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
