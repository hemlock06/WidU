"""낙상 모델 종합 최적화 — 모든 학습구성을 누수없이 비교해 최선 도출.

축(위치별 factorial):
  데이터  : 레거시(2소스) → +SmartFallMM young(3소스)
  고령ADL : 없음 → 추가(음성, 오탐 억제)
  증강    : 없음 → 있음(위치별 회전각, 학습폴드만)
평가(전부 누수없음):
  LODO        : 셋1개 통째로 빼고 학습→테스트 = 미지 출처 일반화(헤드라인)
  고령 FP     : 고령 피험자 GroupKFold = 미지 고령 일상 오탐율
  CV recall   : 풀링 피험자분할 = in-dist recall(하락 금지 가드)
선택 기준: LODO-F1↑ + 고령FP↓ + 젊은낙상 recall 유지. 임계 스윕으로 운영점.
산출 → artifacts/fall_optimization_report.json
"""
from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features
from widu.augment import augment_train, ROTATION_BOUND
from widu.eval.metrics import binary_metrics
from widu.datasets import sisfall, weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)
RS = 0


# ----------------------------- 윈도우 캐시 ----------------------------- #
def _win(arr, src_fs):
    a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
    w = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
    return w if len(w) >= MIN_WIN else None


def cache_source(gen, src_fs):
    """→ list[(window(N,6), label, subj)]"""
    out = []
    for arr, lab, subj, *_ in gen:
        if lab < 0 or len(arr) < 4:
            continue
        w = _win(arr, src_fs)
        if w is not None:
            out.append((np.asarray(w, float), int(lab), subj))
    return out


def feats(windows):
    return np.array([extract_features(w, L2.FS) for w in windows])


def _rf():
    return RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                  random_state=RS, n_jobs=-1)


def _fit_eval(tr_wins, tr_y, tr_g, te_X, te_y, aug, angle):
    if aug:
        W, Y, _ = augment_train(tr_wins, tr_y, tr_g, n_aug=2, seed=RS,
                                max_angle_deg=angle)
        Xtr = feats(W); ytr = Y
    else:
        Xtr = feats(tr_wins); ytr = np.asarray(tr_y)
    clf = _rf().fit(Xtr, ytr)
    proba = clf.predict_proba(te_X)[:, 1]
    return clf, proba


# ----------------------------- 평가들 ----------------------------- #
def lodo(young: dict, elderly, use_elderly, aug, angle, th):
    """young={name:[(w,lab,subj)]}. held-out 한 셋씩. elderly ADL은 학습에만(옵션)."""
    names = list(young)
    feat_cache = {n: feats([w for w, _, _ in young[n]]) for n in names} if not aug else None
    y_cache = {n: np.array([l for _, l, _ in young[n]]) for n in names}
    sens, prec, f1 = [], [], []
    for held in names:
        tr_wins, tr_y, tr_g = [], [], []
        for n in names:
            if n == held:
                continue
            for w, l, s in young[n]:
                tr_wins.append(w); tr_y.append(l); tr_g.append(f"{n}_{s}")
        if use_elderly and elderly is not None:
            for w, l, s in elderly:        # 고령 ADL(음성)
                tr_wins.append(w); tr_y.append(0); tr_g.append(f"OLD_{s}")
        teX = feat_cache[held] if (not aug) else feats([w for w, _, _ in young[held]])
        teY = y_cache[held]
        _, proba = _fit_eval(tr_wins, tr_y, tr_g, teX, teY, aug, angle)
        m = binary_metrics(teY, (proba >= th).astype(int)).summary()
        sens.append(m["sensitivity"]); prec.append(m["precision"]); f1.append(m["f1"])
    return {"sensitivity": round(np.mean(sens), 3), "precision": round(np.mean(prec), 3),
            "f1": round(np.mean(f1), 3)}


def elderly_fp(young: dict, elderly, use_elderly, aug, angle, th):
    """고령 피험자 GroupKFold FP. use_elderly=False면 전체 고령에 FP(학습 미포함)."""
    yw = [w for n in young for w, _, _ in young[n]]
    yy = [l for n in young for _, l, _ in young[n]]
    yg = [f"{n}_{s}" for n in young for _, _, s in young[n]]
    Xo = np.array([w for w, _, _ in elderly], dtype=object)
    go = np.array([s for _, _, s in elderly])
    fps = []
    if not use_elderly:
        teX = feats([w for w, _, _ in elderly])
        _, proba = _fit_eval(list(yw), list(yy), list(yg), teX, np.zeros(len(teX)), aug, angle)
        return {"elderly_fp": round(float((proba >= th).mean()), 3), "mode": "no-elderly-in-train"}
    gkf = GroupKFold(n_splits=5)
    for tr, te in gkf.split(Xo, np.zeros(len(Xo)), go):
        tr_wins = list(yw) + [elderly[i][0] for i in tr]
        tr_y = list(yy) + [0] * len(tr)
        tr_g = list(yg) + [f"OLD_{go[i]}" for i in tr]
        teX = feats([elderly[i][0] for i in te])
        _, proba = _fit_eval(tr_wins, tr_y, tr_g, teX, np.zeros(len(teX)), aug, angle)
        fps.append(float((proba >= th).mean()))
    return {"elderly_fp": round(float(np.mean(fps)), 3), "mode": "subject-split-5fold"}


def cv_recall(young: dict, aug, angle, th):
    """풀링 피험자분할 CV(in-dist recall 가드)."""
    wins = [w for n in young for w, _, _ in young[n]]
    y = np.array([l for n in young for _, l, _ in young[n]])
    g = np.array([f"{n}_{s}" for n in young for _, _, s in young[n]])
    gkf = GroupKFold(n_splits=5)
    sens, prec, f1 = [], [], []
    for tr, te in gkf.split(wins, y, g):
        tr_wins = [wins[i] for i in tr]; tr_y = y[tr]; tr_g = g[tr]
        teX = feats([wins[i] for i in te]); teY = y[te]
        _, proba = _fit_eval(tr_wins, tr_y, tr_g, teX, teY, aug, angle)
        m = binary_metrics(teY, (proba >= th).astype(int)).summary()
        sens.append(m["sensitivity"]); prec.append(m["precision"]); f1.append(m["f1"])
    return {"sensitivity": round(np.mean(sens), 3), "precision": round(np.mean(prec), 3),
            "f1": round(np.mean(f1), 3)}


# ----------------------------- 메인 ----------------------------- #
def build(position):
    if position == "wrist":
        legacy = {
            "WEDA": cache_source(weda.iter_dataset(DATA / "WEDA_raw"), weda.FS),
            "UMAFall": cache_source(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS),
        }
        smm_young = cache_source(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS)
        elderly = [(w, l, s) for w, l, s in
                   cache_source(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS) if l == 0]
        angle = ROTATION_BOUND["watch"]
    else:
        legacy = {
            "SisFall": cache_source(sisfall.iter_dataset(DATA / "SisFall"), sisfall.FS),
            "UMAFall": cache_source(umafall.iter_dataset(DATA / "UMAFall_raw", "WAIST"), umafall.FS),
        }
        smm_young = cache_source(smm.iter_dataset(DATA / "SmartFallMM", "young", "phone"), smm.FS)
        elderly = [(w, l, s) for w, l, s in
                   cache_source(smm.iter_dataset(DATA / "SmartFallMM", "old", "phone"), smm.FS) if l == 0]
        angle = ROTATION_BOUND["phone"]
    return legacy, smm_young, elderly, angle


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    th = L2.FALL_PROBA_TH
    report = {"threshold": th, "rotation_bounds": ROTATION_BOUND}
    for position in ("wrist", "waist"):
        print(f"\n############## {position.upper()} ##############", flush=True)
        legacy, smm_young, elderly, angle = build(position)
        for n in legacy:
            print(f"  {n}: {len(legacy[n])} win (낙상 {sum(l for _,l,_ in legacy[n])})", flush=True)
        print(f"  SMM young: {len(smm_young)} (낙상 {sum(l for _,l,_ in smm_young)}) | "
              f"고령ADL: {len(elderly)} | 회전각 ±{angle}°", flush=True)

        # 구성 정의: (이름, young소스dict, use_elderly, aug)
        with_smm = dict(legacy); with_smm["SmartFallMM"] = smm_young
        configs = [
            ("C1_legacy",            legacy,   False, False),
            ("C2_+SMM",              with_smm, False, False),
            ("C3_+SMM+elderly",      with_smm, True,  False),
            ("C4_+SMM+elderly+aug",  with_smm, True,  True),
        ]
        res = {}
        for name, young, use_eld, aug in configs:
            print(f"\n  [{name}] (aug={aug}, elderly={use_eld}) ...", flush=True)
            r = {
                "lodo": lodo(young, elderly, use_eld, aug, angle, th),
                "elderly_fp": elderly_fp(young, elderly, use_eld, aug, angle, th),
                "cv_recall": cv_recall(young, aug, angle, th),
            }
            res[name] = r
            print(f"    LODO={r['lodo']}  고령FP={r['elderly_fp']}  CV={r['cv_recall']}", flush=True)
        report[position] = res
    out = ROOT / "artifacts" / "fall_optimization_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
