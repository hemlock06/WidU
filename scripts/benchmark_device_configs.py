"""기기 구성 벤치마크 — 워치만 / 폰만 / 둘다(자이로+가속 IMU 낙상).

질문: 같은 낙상을 (a)스마트워치만 (b)스마트폰만 (c)둘다 가져왔을 때 탐지 성능이
어떻게 달라지나?

왜 UMAFall인가: UMAFall은 한 trial(같은 낙상 이벤트)을 손목·허리·주머니 등 여러
위치에서 **동시(동기)** 기록한다. 따라서 같은 낙상에 대해 워치(손목)와 폰(허리)이
무엇을 보는지 정확히 짝지어 비교할 수 있다(다른 단일위치 셋은 불가).

정직성(중요): 배포 모델(wrist/waist)은 학습에 UMAFall을 포함한다 → 그냥 테스트하면
인샘플(낙관). 그래서 **GroupKFold(피험자 분리)** 로, 각 fold마다 테스트 피험자를
제외하고 재학습한 뒤 그 피험자에게만 추론한다. 모든 UMAFall trial이 '자기 피험자를
못 본' 모델의 예측을 받는다(주관 누수 없음). 베이스 학습셋은 배포와 동일 위치 매핑:
  · 워치(손목) = WEDA + UMAFall-WRIST(타 피험자)
  · 폰(허리)   = SisFall + UMAFall-WAIST(타 피험자)   (폰=허리/주머니 위치 모델, D22)

융합('둘다') 로직 = 실제 L5와 동일: 각 기기는 자기 임계로 독립 발화, 시스템은
**OR**(어느 한쪽이라도 발화 → 알람), 양쪽 발화 시 '교차확인'으로 신뢰↑(l5_fusion).
임계: 워치 0.30 / 폰 0.40 (config.FALL_PROBA_TH_BY_SOURCE).

사용: python scripts/benchmark_device_configs.py [--folds 5] [--trees 300]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import extract_window
from widu.datasets import umafall
from widu.falleval import (DATA, MIN_WIN, FS, cache_windows, feats, rf,
                           src_weda, src_sisfall)

TH_WATCH = L2.FALL_PROBA_TH_BY_SOURCE["watch"]   # 0.30
TH_PHONE = L2.FALL_PROBA_TH_BY_SOURCE["phone"]   # 0.40


def umafall_paired():
    """UMAFall trial별로 (손목, 허리) 윈도우를 짝지어 로드. 둘 다 유효한 trial만.
    반환: subjects[], labels[], wrist_wins[], waist_wins[] (인덱스 정렬)."""
    subs, labs, wr, wa = [], [], [], []
    n_csv = n_pair = 0
    for csv in sorted((DATA / "UMAFall_raw").rglob("UMAFall_Subject_*.csv")):
        n_csv += 1
        aw, lw, subj, _ = umafall.load_trial(csv, "WRIST")
        ai, li, _, _ = umafall.load_trial(csv, "WAIST")
        if len(aw) == 0 or len(ai) == 0:
            continue
        ww = extract_window(aw, L2.FS, L2.WIN_SEC, pre_frac=0.75)   # UMAFall은 이미 50Hz
        wi = extract_window(ai, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(ww) < MIN_WIN or len(wi) < MIN_WIN:
            continue
        subs.append(subj); labs.append(int(lw))
        wr.append(np.asarray(ww, float)); wa.append(np.asarray(wi, float))
        n_pair += 1
    print(f"UMAFall: {n_csv} csv → {n_pair} trial(손목·허리 동기 둘 다 유효)")
    return np.array(subs), np.array(labs), wr, wa


def metrics(y, pred):
    y = np.asarray(y); pred = np.asarray(pred)
    fall = y == 1; adl = y == 0
    tp = int((pred & fall).sum()); fn = int((~pred & fall).sum())
    fp = int((pred & adl).sum()); tn = int((~pred & adl).sum())
    recall = tp / max(tp + fn, 1)
    fpr = fp / max(fp + tn, 1)
    prec = tp / max(tp + fp, 1)
    f1 = 2 * prec * recall / max(prec + recall, 1e-9)
    return dict(recall=recall, fpr=fpr, precision=prec, f1=f1,
               tp=tp, fn=fn, fp=fp, tn=tn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--trees", type=int, default=300)
    a = ap.parse_args()

    print("베이스 학습셋 로딩(배포와 동일 위치 매핑)…")
    weda = cache_windows(src_weda(), FS["weda"])                 # 손목 베이스
    sis = cache_windows(src_sisfall(), FS["sisfall"])            # 허리 베이스
    Xw_base = feats([w for w, _, _ in weda]); yw_base = np.array([l for _, l, _ in weda])
    Xa_base = feats([w for w, _, _ in sis]);  ya_base = np.array([l for _, l, _ in sis])
    print(f"  손목 베이스 WEDA: {len(yw_base)} (낙상 {int(yw_base.sum())})")
    print(f"  허리 베이스 SisFall: {len(ya_base)} (낙상 {int(ya_base.sum())})")

    subs, labs, wr, wa = umafall_paired()
    Xw_uma = feats(wr); Xa_uma = feats(wa)

    # GroupKFold(피험자) — 각 trial은 '자기 피험자 미학습' 모델의 예측을 받음
    gkf = GroupKFold(n_splits=a.folds)
    pw = np.full(len(labs), np.nan); pa = np.full(len(labs), np.nan)
    for fold, (tr, te) in enumerate(gkf.split(Xw_uma, labs, groups=subs), 1):
        mw = rf(n_estimators=a.trees)
        mw.fit(np.vstack([Xw_base, Xw_uma[tr]]), np.concatenate([yw_base, labs[tr]]))
        pw[te] = mw.predict_proba(Xw_uma[te])[:, 1]
        ma = rf(n_estimators=a.trees)
        ma.fit(np.vstack([Xa_base, Xa_uma[tr]]), np.concatenate([ya_base, labs[tr]]))
        pa[te] = ma.predict_proba(Xa_uma[te])[:, 1]
        print(f"  fold {fold}/{a.folds}: 학습피험자 {len(set(subs[tr]))} → 테스트 trial {len(te)}")

    assert not np.isnan(pw).any() and not np.isnan(pa).any()
    watch = pw >= TH_WATCH
    phone = pa >= TH_PHONE
    both = watch | phone                 # 시스템 OR(L5)
    both_corrob = watch & phone          # 양쪽 발화(교차확인=고신뢰)

    print(f"\n{'='*64}\n기기 구성 벤치마크 (UMAFall {len(labs)} trial, "
          f"낙상 {int(labs.sum())}/ADL {int((labs==0).sum())}; 피험자 {len(set(subs))})")
    print(f"임계: 워치≥{TH_WATCH} / 폰≥{TH_PHONE} · 융합=OR(L5와 동일)\n{'='*64}")
    hdr = f"{'구성':<14}{'recall':>8}{'오탐율':>8}{'precision':>11}{'F1':>7}  (TP/FN  FP/TN)"
    print(hdr)
    for name, pred in [("① 워치만", watch), ("② 폰만", phone), ("③ 둘다(OR)", both)]:
        m = metrics(labs, pred)
        print(f"{name:<14}{m['recall']:>8.3f}{m['fpr']:>8.3f}{m['precision']:>11.3f}"
              f"{m['f1']:>7.3f}  ({m['tp']}/{m['fn']}  {m['fp']}/{m['tn']})")
    mc = metrics(labs, both_corrob)
    print(f"\n참고) 양쪽 동시발화(교차확인·고신뢰): "
          f"낙상 {mc['tp']}/{int(labs.sum())} 회수 · ADL 동시오탐 {mc['fp']}/{int((labs==0).sum())}")

    # 단일기기가 놓친 낙상을 다른 기기가 건진 비율(둘다의 핵심 효익)
    miss_watch_caught_phone = int(((~watch) & phone & (labs == 1)).sum())
    miss_phone_caught_watch = int((watch & (~phone) & (labs == 1)).sum())
    nf = int(labs.sum())
    print(f"보완) 워치 놓침→폰이 건짐: {miss_watch_caught_phone}/{nf} · "
          f"폰 놓침→워치가 건짐: {miss_phone_caught_watch}/{nf}")

    # --- 회색지대 교차확인 분석(가설 검증) --- #
    # 질문: 워치·폰이 둘 다 '약한 의심'(SOFT≤proba<임계, 현재 self_check行)일 때
    # 그게 단일 의심보다 정밀한가? '확신 발화'에 근접하나? → 격상/단축확인 정당화 여부.
    SOFT = L2.FALL_PROBA_SOFT
    falls = labs == 1
    wg = (pw >= SOFT) & (pw < TH_WATCH)   # 워치 회색지대
    pg = (pa >= SOFT) & (pa < TH_PHONE)   # 폰 회색지대
    cw = pw >= TH_WATCH; cp = pa >= TH_PHONE   # 확신(≥임계)

    def line(name, m):
        n = int(m.sum()); f = int((m & falls).sum())
        p = f / n if n else float("nan")
        print(f"  {name:<18} trial {n:>4} · 낙상 {f:>4} · ADL {n-f:>4} · precision {p:.3f}")

    print(f"\n{'='*64}\n회색지대 교차확인 분석 (SOFT={SOFT} ≤ proba < 임계; 현재 self_check行)\n{'='*64}")
    print("[회색지대]")
    line("워치 회색 단독", wg)
    line("폰 회색 단독", pg)
    line("양쪽 회색 동시", wg & pg)
    print("[비교: 확신(≥임계)]")
    line("워치 확신 단독", cw)
    line("폰 확신 단독", cp)
    line("양쪽 확신 동시", cw & cp)
    # 양쪽 회색이 현재 놓치는 게 아니라 self_check로 가는 낙상 — 이들 중 진짜 낙상 비율이
    # 확신에 근접하면 '양쪽 회색 → 격상' 정당, ADL이 섞이면 self_check 유지가 옳음.
    bg = wg & pg
    bg_fall = int((bg & falls).sum()); bg_adl = int((bg & ~falls).sum())
    print(f"\n판정 근거: 양쪽 회색 동시 = 낙상 {bg_fall} vs ADL {bg_adl} "
          f"→ {'정밀(격상 검토 가치)' if bg_fall and bg_adl == 0 else 'ADL 혼입(self_check 유지)' if bg_adl else '표본 없음'}")


if __name__ == "__main__":
    main()
