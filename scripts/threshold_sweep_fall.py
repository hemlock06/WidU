"""임계 스윕 — 선택 구성(손목 C3, 허리 C1)에서 운영점 최적화.

폴드당 1회만 학습하고 저장된 확률에 여러 임계를 적용(효율적).
손목 C3(+SMM+고령ADL): 민감도 회복 임계 탐색(고령 FP 억제 유지).
허리 C1(레거시): 현 임계 적정성 확인.
산출 → artifacts/threshold_sweep_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features
from widu.eval.metrics import binary_metrics
from widu.datasets import sisfall, weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)
THS = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]


def cache(gen, src_fs, only_adl=False):
    out = []
    for arr, lab, subj, *_ in gen:
        if lab < 0 or len(arr) < 4 or (only_adl and lab != 0):
            continue
        a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
        w = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(w) >= MIN_WIN:
            out.append((np.asarray(w, float), int(lab), subj))
    return out


def feats(W):
    return np.array([extract_features(w, L2.FS) for w in W])


def _rf():
    return RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                  random_state=0, n_jobs=-1)


def lodo_probas(young: dict, elderly):
    """held-out 폴드별 (y, proba) 수집(임계 무관)."""
    names = list(young)
    folds = []
    for held in names:
        trw, trY = [], []
        for n in names:
            if n == held:
                continue
            for w, l, _ in young[n]:
                trw.append(w); trY.append(l)
        if elderly:
            for w, _, _ in elderly:
                trw.append(w); trY.append(0)
        clf = _rf().fit(feats(trw), np.array(trY))
        teX = feats([w for w, _, _ in young[held]])
        teY = np.array([l for _, l, _ in young[held]])
        folds.append((teY, clf.predict_proba(teX)[:, 1]))
    return folds


def elderly_probas(young: dict, elderly):
    yw = [w for n in young for w, _, _ in young[n]]
    yy = [l for n in young for _, l, _ in young[n]]
    Xo = np.array([w for w, _, _ in elderly], dtype=object)
    go = np.array([s for _, _, s in elderly])
    probs = []
    for tr, te in GroupKFold(5).split(Xo, np.zeros(len(Xo)), go):
        trw = list(yw) + [elderly[i][0] for i in tr]
        trY = list(yy) + [0] * len(tr)
        clf = _rf().fit(feats(trw), np.array(trY))
        teX = feats([elderly[i][0] for i in te])
        probs.append(clf.predict_proba(teX)[:, 1])
    return probs


def sweep(lodo_folds, eld_probs):
    rows = {}
    for th in THS:
        s, p, f = [], [], []
        for y, pr in lodo_folds:
            m = binary_metrics(y, (pr >= th).astype(int)).summary()
            s.append(m["sensitivity"]); p.append(m["precision"]); f.append(m["f1"])
        fp = np.mean([float((pr >= th).mean()) for pr in eld_probs]) if eld_probs else None
        rows[f"{th:.2f}"] = {
            "lodo_sens": round(np.mean(s), 3), "lodo_prec": round(np.mean(p), 3),
            "lodo_f1": round(np.mean(f), 3),
            "elderly_fp": round(float(fp), 3) if fp is not None else None,
        }
    return rows


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    report = {}

    # 손목 C3: WEDA + UMAFall + SMM young + 고령 ADL
    print("=== 손목 C3 임계 스윕 ===", flush=True)
    young_w = {
        "WEDA": cache(weda.iter_dataset(DATA / "WEDA_raw"), weda.FS),
        "UMAFall": cache(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS),
        "SmartFallMM": cache(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS),
    }
    eld_w = [t for t in cache(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS) if t[1] == 0]
    report["wrist_C3"] = sweep(lodo_probas(young_w, eld_w), elderly_probas(young_w, eld_w))
    print(json.dumps(report["wrist_C3"], ensure_ascii=False, indent=2))

    # 허리 C1 레거시: SisFall + UMAFall (고령 미포함 → 전체 고령에 FP)
    print("\n=== 허리 C1 레거시 임계 스윕 ===", flush=True)
    young_a = {
        "SisFall": cache(sisfall.iter_dataset(DATA / "SisFall"), sisfall.FS),
        "UMAFall": cache(umafall.iter_dataset(DATA / "UMAFall_raw", "WAIST"), umafall.FS),
    }
    eld_a = [t for t in cache(smm.iter_dataset(DATA / "SmartFallMM", "old", "phone"), smm.FS) if t[1] == 0]
    # 레거시는 고령 미학습 → 전체 고령에 단일 FP(임계별)
    yw = [w for n in young_a for w, _, _ in young_a[n]]
    yy = [l for n in young_a for _, l, _ in young_a[n]]
    clf = _rf().fit(feats(yw), np.array(yy))
    eldX = feats([w for w, _, _ in eld_a])
    eld_pr_single = [clf.predict_proba(eldX)[:, 1]]
    report["waist_C1"] = sweep(lodo_probas(young_a, None), eld_pr_single)
    print(json.dumps(report["waist_C1"], ensure_ascii=False, indent=2))

    (ROOT / "artifacts" / "threshold_sweep_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] artifacts/threshold_sweep_report.json")


if __name__ == "__main__":
    main()
