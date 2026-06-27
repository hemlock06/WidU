"""다중셋 결합 학습 — 일반화(특히 정밀도) robustness 향상.

cross-dataset 결과: 민감도는 전이되나 정밀도는 기기별로 하락 → 더 다양한 데이터로 학습.
  손목 모델 = WEDA + UMAFall(wrist)
  허리 모델 = SisFall + UMAFall(waist)
피험자 그룹에 데이터셋 접두사 → GroupKFold 가 자연히 dataset 혼합 폴드(일반화 인지 CV).
배포 경로(MODEL_PATH_WRIST/WAIST)에 덮어씀.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.falleval import feats  # 공유 헬퍼(DRY)
from widu.datasets import weda, umafall, sisfall
from widu.preprocess import extract_window, resample_antialiased
from widu.l2_fall import FALL_FEATURES
from widu.augment import augment_train
from widu.eval.metrics import binary_metrics


def _win(arr):
    w = extract_window(arr, L2.FS, L2.WIN_SEC, 0.75)
    return w if len(w) >= int(L2.WIN_SEC * L2.FS * 0.5) else None


def wrist_windows():
    W, Y, G = [], [], []
    for arr, lab, subj, ft in weda.iter_dataset(ROOT / "data" / "WEDA_raw"):
        w = _win(arr)
        if w is not None:
            W.append(w); Y.append(lab); G.append("WEDA_" + subj)
    for arr, lab, subj, age in umafall.iter_dataset(ROOT / "data" / "UMAFall_raw", "WRIST"):
        w = _win(arr)
        if w is not None:
            W.append(w); Y.append(lab); G.append("UMA_" + subj)
    return W, np.array(Y), np.array(G)


def waist_windows():
    W, Y, G = [], [], []
    for arr, lab, subj in sisfall.iter_dataset(ROOT / "data" / "SisFall"):
        arr = resample_antialiased(arr, sisfall.FS, L2.FS)
        w = _win(arr)
        if w is not None:
            W.append(w); Y.append(lab); G.append("SIS_" + subj)
    for arr, lab, subj, age in umafall.iter_dataset(ROOT / "data" / "UMAFall_raw", "WAIST"):
        w = _win(arr)
        if w is not None:
            W.append(w); Y.append(lab); G.append("UMA_" + subj)
    return W, np.array(Y), np.array(G)




def train_and_save(W, Y, G, out, tag):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    import joblib
    print(f"[{tag}] 결합 {len(Y)}윈도우 (낙상 {sum(Y)}, 피험자 {len(set(G))}, 데이터셋 {len(set(g.split('_')[0] for g in G))})")
    se, pr, f1 = [], [], []
    for tr, te in GroupKFold(5).split(np.arange(len(Y)), Y, G):
        Wtr, Ytr, _ = augment_train([W[i] for i in tr], Y[tr], G[tr], n_aug=2, seed=0)
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1).fit(feats(Wtr), Ytr)
        m = binary_metrics(Y[te], (clf.predict_proba(feats([W[i] for i in te]))[:, 1] >= L2.FALL_PROBA_TH).astype(int))
        se.append(m.sensitivity); pr.append(m.precision); f1.append(m.f1)
    print(f"[{tag}] 혼합폴드 CV  민감도={np.mean(se):.3f} 정밀도={np.mean(pr):.3f} F1={np.mean(f1):.3f}")
    Wa, Ya, _ = augment_train(W, Y, G, n_aug=2, seed=0)
    final = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                   random_state=0, n_jobs=-1).fit(feats(Wa), Ya)
    joblib.dump(final, out)
    print(f"[{tag}] 저장 → {out}")


def main():
    Ww, Yw, Gw = wrist_windows()
    train_and_save(Ww, Yw, Gw, L2.MODEL_PATH_WRIST, "손목(WEDA+UMAFall)")
    Wa, Ya, Ga = waist_windows()
    train_and_save(Wa, Ya, Ga, L2.MODEL_PATH_WAIST, "허리(SisFall+UMAFall)")


if __name__ == "__main__":
    main()
