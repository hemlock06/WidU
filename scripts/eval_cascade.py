"""파형-무관 캐스케이드 효과 측정 — 분류기 미탐을 '충격+무활동'이 복구하나?

문제: L2가 proba>=th에만 의존 → 고령 소프트폴(분류기 약점)을 놓치면 후보조차 없음.
가설: hard impact(큰 SMV)는 분류기와 무관하게 낙상 신호. '충격 OR 분류기' 결합 recall 측정.
데이터: WEDA(손목, 소프트폴 F05~08=앉다가/실신=고령형) + SisFall(허리).
 - 분류기 recall vs (분류기 OR impact>=Hg) recall, 특히 소프트폴에서 복구량
 - ADL의 impact>=Hg 비율(=사후 무활동 게이트가 걸러야 할 잠재 FP)
 - hard 임계 후보 스윕
산출 → artifacts/cascade_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features, FallModel, _smv
from widu.datasets import weda, sisfall

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)
SOFT = {"F05", "F06", "F07", "F08"}   # WEDA 고령형 소프트폴


def rows_weda():
    m = FallModel(L2.MODEL_PATH_WRIST)
    th = L2.FALL_PROBA_TH_BY_SOURCE["watch"]
    out = []
    for arr, lab, subj, ftype in weda.iter_dataset(DATA / "WEDA_raw"):
        win = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < MIN_WIN:
            continue
        proba = m.fall_proba(extract_features(np.asarray(win, float), L2.FS))
        impact = float(_smv(np.asarray(win, float)[:, :3]).max())
        out.append((lab, proba, impact, ftype, th))
    return out


def rows_sisfall():
    m = FallModel(L2.MODEL_PATH_WAIST)
    th = L2.FALL_PROBA_TH_BY_SOURCE["phone"]
    out = []
    for arr, lab, meta in sisfall.iter_dataset(DATA / "SisFall"):
        a = resample_antialiased(arr, sisfall.FS, L2.FS)
        win = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < MIN_WIN:
            continue
        proba = m.fall_proba(extract_features(np.asarray(win, float), L2.FS))
        impact = float(_smv(np.asarray(win, float)[:, :3]).max())
        out.append((lab, proba, impact, "fall" if lab else "adl", th))
    return out


def analyze(rows, name, soft_set=None):
    th = rows[0][4]
    falls = [(p, im, ft) for (l, p, im, ft, _) in rows if l == 1]
    adls = [(p, im) for (l, p, im, ft, _) in rows if l == 0]
    res = {"n_fall": len(falls), "n_adl": len(adls), "clf_th": th}
    clf_rec = np.mean([p >= th for p, im, ft in falls]) if falls else 0
    res["clf_recall"] = round(float(clf_rec), 3)
    # hard 임계 스윕
    sweep = {}
    for Hg in [2.0, 2.3, 2.5, 2.8, 3.0]:
        comb = np.mean([(p >= th) or (im >= Hg) for p, im, ft in falls]) if falls else 0
        adl_hard = np.mean([im >= Hg for p, im in adls]) if adls else 0   # 무활동 게이트 전 잠재FP
        sweep[f"H{Hg}"] = {"combined_recall": round(float(comb), 3),
                           "adl_impact_ge_H": round(float(adl_hard), 3)}
    res["hard_sweep"] = sweep
    if soft_set is not None:
        soft = [(p, im) for p, im, ft in falls if ft in soft_set]
        if soft:
            sc = np.mean([p >= th for p, im in soft])
            sh = np.mean([(p >= th) or (im >= 2.5) for p, im in soft])
            res["soft_fall"] = {"n": len(soft), "clf_recall": round(float(sc), 3),
                                "combined_recall@2.5": round(float(sh), 3),
                                "recovered": round(float(sh - sc), 3)}
    print(f"\n=== {name} ===")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return res


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    report = {}
    report["weda_wrist"] = analyze(rows_weda(), "WEDA 손목(소프트폴 포함)", soft_set=SOFT)
    report["sisfall_waist"] = analyze(rows_sisfall(), "SisFall 허리")
    (ROOT / "artifacts" / "cascade_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[saved] artifacts/cascade_report.json")


if __name__ == "__main__":
    main()
