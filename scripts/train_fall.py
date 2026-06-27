"""낙상 탐지 모델(L2) 학습 — SisFall 기반, 누수 없는 증강 파이프라인.

핵심 순서(중요):
  1) 윈도우 생성: 안티앨리어싱 리샘플(200→50Hz) + 일치 윈도우(extract_window).
  2) 피험자 단위 분할(GroupKFold) — 같은 사람 train/test 혼입 금지.
  3) **분할 이후, 학습 폴드에만** 증강(rotate/jitter/scale/time_warp).
  4) 특징추출은 학습/추론 동일 함수(extract_features).
최종 모델은 전체 실데이터 + 증강으로 학습해 저장(배포엔 홀드아웃 없음).

사용: python scripts/train_fall.py --root data/SisFall --n_aug 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.falleval import feats  # 공유 헬퍼(DRY)
from widu.l2_fall import FALL_FEATURES
from widu.preprocess import resample_antialiased, extract_window
from widu.augment import augment_train
from widu.datasets import sisfall, synthetic
from widu.eval.metrics import binary_metrics


def windows_from_sisfall(root: Path):
    W, Y, G = [], [], []
    for arr, lab, subj in sisfall.iter_dataset(root):
        arr = resample_antialiased(arr, sisfall.FS, L2.FS)
        win = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < int(L2.WIN_SEC * L2.FS * 0.5):
            continue
        W.append(win); Y.append(lab); G.append(subj)
    print(f"  SisFall 윈도우 {len(Y)}개 (낙상 {sum(Y)}, ADL {len(Y)-sum(Y)})")
    return W, np.array(Y), np.array(G)


def windows_synthetic(n_each: int = 300):
    W, Y, G = [], [], []
    for i in range(n_each):
        W.append(synthetic.fall_window(L2.FS, L2.WIN_SEC, seed=i)); Y.append(1); G.append(f"syn{i%10}")
        W.append(synthetic.adl_window(L2.FS, L2.WIN_SEC, seed=1000+i)); Y.append(0); G.append(f"syn{i%10}")
    print(f"  합성 윈도우 {len(Y)}개")
    return W, np.array(Y), np.array(G)


def windows_from_weda(root: Path):
    """WEDA-FALL(손목·50Hz) — 리샘플 불필요(이미 50Hz 보간)."""
    from widu.datasets import weda
    W, Y, G = [], [], []
    for arr, lab, subj, ft in weda.iter_dataset(root):
        win = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < int(L2.WIN_SEC * L2.FS * 0.5):
            continue
        W.append(win); Y.append(lab); G.append(subj)
    print(f"  WEDA 손목 윈도우 {len(Y)}개 (낙상 {sum(Y)}, ADL {len(Y)-sum(Y)})")
    return W, np.array(Y), np.array(G)




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", choices=["sisfall", "weda"], default="sisfall")
    ap.add_argument("--root", default=str(ROOT / "data" / "SisFall"))
    ap.add_argument("--out", default=str(L2.MODEL_PATH))
    ap.add_argument("--n_aug", type=int, default=2)
    a = ap.parse_args()

    root = Path(a.root)
    if a.dataset == "weda" and root.exists():
        print(f"[train] WEDA 손목: {root}")
        W, Y, G = windows_from_weda(root)
    elif root.exists() and any(root.rglob("*.txt")):
        print(f"[train] SisFall: {root}")
        W, Y, G = windows_from_sisfall(root)
    else:
        print("[train] 데이터 미발견 → 합성(스모크).")
        W, Y, G = windows_synthetic()

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    import joblib

    W = np.array(W, dtype=object)
    gkf = GroupKFold(n_splits=min(5, len(set(G))))
    senss, specs, precs, f1s = [], [], [], []
    for tr, te in gkf.split(W, Y, G):
        # 분할 이후, 학습셋만 증강
        Wtr_aug, Ytr_aug, _ = augment_train([W[i] for i in tr], Y[tr], G[tr],
                                            n_aug=a.n_aug, seed=0)
        Xtr = feats(Wtr_aug)
        Xte = feats([W[i] for i in te])               # 테스트는 원본만(증강 금지)
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1)
        clf.fit(Xtr, Ytr_aug)
        m = binary_metrics(Y[te], clf.predict(Xte))
        senss.append(m.sensitivity); specs.append(m.specificity)
        precs.append(m.precision); f1s.append(m.f1)
    print(f"[CV·피험자분할] 민감도={np.mean(senss):.3f} 특이도={np.mean(specs):.3f} "
          f"정밀도={np.mean(precs):.3f} F1={np.mean(f1s):.3f}")

    # 최종: 전체 + 증강
    Wall, Yall, _ = augment_train(list(W), Y, G, n_aug=a.n_aug, seed=0)
    final = RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                   random_state=0, n_jobs=-1)
    final.fit(feats(Wall), Yall)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, a.out)
    print(f"[save] {a.out}  (학습표본 {len(Yall)} = 원본 {len(Y)} + 증강)")
    imp = sorted(zip(FALL_FEATURES, final.feature_importances_), key=lambda x: -x[1])
    print("[중요 피처]", ", ".join(f"{k}={v:.2f}" for k, v in imp[:6]))


if __name__ == "__main__":
    main()
