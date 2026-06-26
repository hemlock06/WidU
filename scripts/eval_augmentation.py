"""증강 efficacy A/B 검증 — 실 SisFall, 피험자분할 동일 폴드에서 증강有/無 비교.

11패스가 '정확성'을 봤다면, 이건 '증강이 실제로 일반화를 높이는가(efficacy)'를 본다.
같은 train/test 분할에서:
   A) 증강 없음(원본만)  vs  B) 학습셋만 증강
테스트셋은 양쪽 동일(원본만) → 공정 비교.
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
from widu.datasets import sisfall
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features
from widu.augment import augment_train
from widu.eval.metrics import binary_metrics


def load_windows(root: Path):
    W, Y, G = [], [], []
    t0 = time.time()
    for arr, lab, subj in sisfall.iter_dataset(root):
        arr = resample_antialiased(arr, sisfall.FS, L2.FS)
        w = extract_window(arr, L2.FS, L2.WIN_SEC, 0.75)
        if len(w) < int(L2.WIN_SEC * L2.FS * 0.5):
            continue
        W.append(w); Y.append(lab); G.append(subj)
    print(f"  로드 {len(Y)}윈도우 (낙상 {sum(Y)}, ADL {len(Y)-sum(Y)}, 피험자 {len(set(G))}) {time.time()-t0:.0f}s")
    return W, np.array(Y), np.array(G)


def feats(ws):
    return np.array([extract_features(np.asarray(w, float), L2.FS) for w in ws])


def run_cv(W, Y, G, n_aug):
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    Wl = list(W)
    out = []
    for tr, te in GroupKFold(n_splits=5).split(Wl, Y, G):
        if n_aug > 0:
            Wtr, Ytr, _ = augment_train([Wl[i] for i in tr], Y[tr], G[tr],
                                        n_aug=n_aug, seed=0)
        else:
            Wtr, Ytr = [Wl[i] for i in tr], Y[tr]
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1)
        clf.fit(feats(Wtr), Ytr)
        m = binary_metrics(Y[te], clf.predict(feats([Wl[i] for i in te])))
        out.append((m.sensitivity, m.specificity, m.precision, m.f1))
    a = np.array(out).mean(0)
    return {"sensitivity": round(a[0], 4), "specificity": round(a[1], 4),
            "precision": round(a[2], 4), "f1": round(a[3], 4)}


def main():
    root = ROOT / "data" / "SisFall"
    if not (root.exists() and any(root.rglob("*.txt"))):
        print("SisFall 미발견. scripts/download_data.py 또는 GitHub 릴리스로 data/SisFall 준비.")
        return
    W, Y, G = load_windows(root)
    print("[A] 증강 없음 CV..."); a = run_cv(W, Y, G, n_aug=0)
    print("    ", a)
    print("[B] 증강 있음 CV (n_aug=2, 학습셋만)..."); b = run_cv(W, Y, G, n_aug=2)
    print("    ", b)
    delta = {k: round(b[k] - a[k], 4) for k in a}
    report = {"no_aug": a, "with_aug": b, "delta(B-A)": delta,
              "n_windows": int(len(Y)), "n_subjects": int(len(set(G)))}
    out = ROOT / "artifacts" / "augmentation_efficacy.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== 증강 efficacy (피험자분할 CV) ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    verdict = "증강이 F1 향상" if delta["f1"] > 0.005 else ("중립/미미" if abs(delta["f1"]) <= 0.005 else "증강이 악화")
    print(f"\n판정: {verdict} (ΔF1={delta['f1']:+.4f})")
    print(f"[saved] {out}")


if __name__ == "__main__":
    main()
