"""전송 레이트 강건성 — '제안된 전송 스펙(50Hz 배치)이면 지금 성능이 유지되나?'

배경: WIDYU 앱 전송 구상 = 워치(IMU) 1초/회·폰(IMU) 3초/회 배치. 핵심은 전송 간격이
아니라 '배치 안 샘플레이트'. WidU 모델은 50Hz(L2.FS)에서 학습·평가됨. 디바이스가
진짜 50Hz를 주면 성능이 유지될까? 미만이면 얼마나 깨질까?

방법: 배포와 동일하게 모델은 **깨끗한 50Hz로 학습**(GroupKFold 피험자 분리), 테스트
입력만 **레이트 R로 열화**(50→R 안티앨리어스 다운샘플 → R→50 복원 = R/2Hz 위 정보 손실)
후 추론. 디바이스가 R Hz로 줄 때 '배포 모델이 받는 입력'을 그대로 모사.

R=50(스펙 충족)이 깨끗한 device 벤치마크와 일치하면 → '스펙 지키면 성능 유지' 확정.
R<50은 미달 시 손실 정량화(스펙 바닥선 근거).

사용: python scripts/benchmark_transmission_rate.py [--folds 5]
"""
from __future__ import annotations

import argparse
import numpy as np
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import extract_window, resample_antialiased
from widu.datasets import umafall
from widu.falleval import (DATA, MIN_WIN, FS, cache_windows, feats, rf,
                           src_weda, src_sisfall)

TH_WATCH = L2.FALL_PROBA_TH_BY_SOURCE["watch"]
TH_PHONE = L2.FALL_PROBA_TH_BY_SOURCE["phone"]
RATES = [50.0, 25.0, 12.5]   # 50=스펙, 그 미만=미달 시나리오


def umafall_paired():
    subs, labs, wr, wa = [], [], [], []
    for csv in sorted((DATA / "UMAFall_raw").rglob("UMAFall_Subject_*.csv")):
        aw, lw, subj, _ = umafall.load_trial(csv, "WRIST")
        ai, li, _, _ = umafall.load_trial(csv, "WAIST")
        if len(aw) == 0 or len(ai) == 0:
            continue
        ww = extract_window(aw, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        wi = extract_window(ai, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(ww) < MIN_WIN or len(wi) < MIN_WIN:
            continue
        subs.append(subj); labs.append(int(lw))
        wr.append(np.asarray(ww, float)); wa.append(np.asarray(wi, float))
    return np.array(subs), np.array(labs), wr, wa


def degrade(win: np.ndarray, rate: float) -> np.ndarray:
    """50Hz 윈도우를 'rate Hz 센서가 봤을 정보'로 열화(안티앨리어스 다운→업)."""
    if rate >= L2.FS:
        return win
    lo = resample_antialiased(win, L2.FS, rate)
    return resample_antialiased(lo, rate, L2.FS)


def metrics(y, pred):
    y = np.asarray(y); pred = np.asarray(pred)
    fall = y == 1; adl = y == 0
    tp = int((pred & fall).sum()); fn = int((~pred & fall).sum())
    fp = int((pred & adl).sum()); tn = int((~pred & adl).sum())
    rec = tp / max(tp + fn, 1); fpr = fp / max(fp + tn, 1)
    prec = tp / max(tp + fp, 1)
    f1 = 2 * prec * rec / max(prec + rec, 1e-9)
    return rec, fpr, prec, f1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=300)
    a = ap.parse_args()

    print("베이스(깨끗한 50Hz) 로딩…")
    weda = cache_windows(src_weda(), FS["weda"])
    sis = cache_windows(src_sisfall(), FS["sisfall"])
    Xw_base = feats([w for w, _, _ in weda]); yw = np.array([l for _, l, _ in weda])
    Xa_base = feats([w for w, _, _ in sis]); ya = np.array([l for _, l, _ in sis])

    subs, labs, wr, wa = umafall_paired()
    Xw_uma = feats(wr); Xa_uma = feats(wa)   # 학습용(깨끗)
    print(f"UMAFall 페어 {len(labs)} trial(낙상 {int(labs.sum())}/ADL {int((labs==0).sum())})")

    # 모델은 깨끗한 50Hz로 1회 학습(배포 규약) → fold별 보관
    gkf = GroupKFold(n_splits=a.folds)
    folds = []
    for tr, te in gkf.split(Xw_uma, labs, groups=subs):
        mw = rf(n_estimators=a.trees)
        mw.fit(np.vstack([Xw_base, Xw_uma[tr]]), np.concatenate([yw, labs[tr]]))
        ma = rf(n_estimators=a.trees)
        ma.fit(np.vstack([Xa_base, Xa_uma[tr]]), np.concatenate([ya, labs[tr]]))
        folds.append((mw, ma, te))

    print(f"\n{'='*70}\n전송 레이트 강건성 (테스트 입력만 R Hz로 열화, 배포 모델은 50Hz 학습)")
    print(f"{'='*70}")
    print(f"{'레이트':<10}{'구성':<12}{'recall':>8}{'오탐율':>8}{'precision':>11}{'F1':>7}")
    base50 = {}
    for R in RATES:
        pw = np.full(len(labs), np.nan); pa = np.full(len(labs), np.nan)
        for mw, ma, te in folds:
            Xw_te = feats([degrade(wr[i], R) for i in te])
            Xa_te = feats([degrade(wa[i], R) for i in te])
            pw[te] = mw.predict_proba(Xw_te)[:, 1]
            pa[te] = ma.predict_proba(Xa_te)[:, 1]
        watch = pw >= TH_WATCH; phone = pa >= TH_PHONE; both = watch | phone
        tag = f"{R:g}Hz" + (" ★스펙" if R == 50 else "")
        for i, (name, pred) in enumerate([("워치만", watch), ("폰만", phone), ("둘다", both)]):
            rec, fpr, prec, f1 = metrics(labs, pred)
            lead = tag if i == 0 else ""
            print(f"{lead:<10}{name:<12}{rec:>8.3f}{fpr:>8.3f}{prec:>11.3f}{f1:>7.3f}")
            if R == 50:
                base50[name] = (rec, fpr, f1)
        print("-" * 52)

    print("\n해석:")
    print("· 50Hz(스펙) 행이 기존 device 벤치마크와 일치하면 → 스펙 지키면 성능 유지.")
    print("· 25/12.5Hz는 디바이스가 50Hz 미만으로 줄 때의 손실 → 스펙 바닥선(≥50Hz) 근거.")


if __name__ == "__main__":
    main()
