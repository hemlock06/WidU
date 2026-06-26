"""손목 강화 2단계 — 특징 공학. 분류기로 안 오르면 더 변별력 있는 특징을 시험.

추가 특징(낙상 vs 손동작 변별, 스케일/회전 강건 지향):
  - SMV 첨도·왜도(충격 스파이크→고첨도)
  - 스펙트럼: 지배주파수, 1~3Hz/3~8Hz 대역에너지비(손동작=율동적 저주파, 낙상=충격성 광대역)
  - 피크 수(손동작=다중피크, 낙상=단일 큰충격)
  - 사후정착비(피크 후/전 에너지)·자기상관 피크(주기성=ADL)
  - gyro-accel 상관
LODO로 base 대비 향상 여부 정직 비교(RF·ExtraTrees). 안 오르면 데이터 한계 확정.
산출 → artifacts/wrist_features_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scipy.stats import kurtosis, skew
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features
from widu.eval.metrics import binary_metrics
from widu.datasets import weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)
TH = L2.FALL_PROBA_TH_BY_SOURCE["watch"]


def _smv(acc):
    return np.sqrt((acc ** 2).sum(axis=1))


def extra_feats(win, fs=L2.FS):
    acc = win[:, 0:3].astype(float); gyro = win[:, 3:6].astype(float)
    smv = _smv(acc); n = len(smv)
    s0 = smv - smv.mean()
    # 첨도/왜도
    kurt = float(kurtosis(smv)) if n > 3 else 0.0
    sk = float(skew(smv)) if n > 2 else 0.0
    # 스펙트럼
    fftmag = np.abs(np.fft.rfft(s0))
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    tot = fftmag.sum() + 1e-9
    dom = float(freqs[np.argmax(fftmag)]) if len(fftmag) > 1 else 0.0
    band_lo = float(fftmag[(freqs >= 1) & (freqs < 3)].sum() / tot)
    band_hi = float(fftmag[(freqs >= 3) & (freqs < 8)].sum() / tot)
    # 피크 수(평균+1std 초과 국소최대)
    thr = smv.mean() + smv.std()
    peaks = int(((smv[1:-1] > smv[:-2]) & (smv[1:-1] > smv[2:]) & (smv[1:-1] > thr)).sum()) if n > 2 else 0
    # 사후정착비
    pi = int(np.argmax(smv))
    pre_e = float((s0[:max(pi, 1)] ** 2).mean())
    post_e = float((s0[pi:] ** 2).mean()) if pi < n - 1 else 0.0
    settle = post_e / (pre_e + 1e-9)
    # 자기상관 1차피크(주기성)
    ac = np.correlate(s0, s0, "full")[n - 1:]
    ac = ac / (ac[0] + 1e-9)
    acpk = float(ac[1:].max()) if n > 2 else 0.0
    # gyro-accel 상관(magnitude)
    gmag = _smv(gyro)
    cc = float(np.corrcoef(smv, gmag)[0, 1]) if n > 2 and gmag.std() > 0 else 0.0
    return np.array([kurt, sk, dom, band_lo, band_hi, peaks, settle, acpk, cc], float)


def cache_windows(gen, src_fs, only_adl=False):
    out = []
    for arr, lab, subj, *_ in gen:
        if lab < 0 or len(arr) < 4 or (only_adl and lab != 0):
            continue
        a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
        w = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(w) >= MIN_WIN:
            out.append((np.asarray(w, float), int(lab), subj))
    return out


def feats(wins, extended):
    if extended:
        return np.array([np.concatenate([extract_features(w, L2.FS), extra_feats(w)]) for w in wins])
    return np.array([extract_features(w, L2.FS) for w in wins])


def _mk(name):
    if name == "RF":
        return RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=0, n_jobs=-1)
    return ExtraTreesClassifier(n_estimators=400, class_weight="balanced", random_state=0, n_jobs=-1)


def lodo_fp(srcwins, eldwins, extended, clf_name):
    names = list(srcwins)
    Xs = {n: feats([w for w, _, _ in srcwins[n]], extended) for n in names}
    ys = {n: np.array([l for _, l, _ in srcwins[n]]) for n in names}
    Xo = feats([w for w, _, _ in eldwins], extended)
    go = np.array([s for _, _, s in eldwins])
    s, p, f = [], [], []
    for held in names:
        Xtr = np.vstack([Xs[n] for n in names if n != held] + [Xo])
        ytr = np.concatenate([ys[n] for n in names if n != held] + [np.zeros(len(Xo), int)])
        clf = _mk(clf_name).fit(Xtr, ytr)
        pr = clf.predict_proba(Xs[held])[:, 1]
        m = binary_metrics(ys[held], (pr >= TH).astype(int)).summary()
        s.append(m["sensitivity"]); p.append(m["precision"]); f.append(m["f1"])
    yw = np.vstack([Xs[n] for n in names]); yy = np.concatenate([ys[n] for n in names])
    fps = []
    for tr, te in GroupKFold(5).split(Xo, np.zeros(len(Xo)), go):
        clf = _mk(clf_name).fit(np.vstack([yw, Xo[tr]]), np.concatenate([yy, np.zeros(len(tr), int)]))
        fps.append(float((clf.predict_proba(Xo[te])[:, 1] >= TH).mean()))
    return {"lodo_sens": round(np.mean(s), 3), "lodo_prec": round(np.mean(p), 3),
            "lodo_f1": round(np.mean(f), 3), "elderly_fp": round(float(np.mean(fps)), 3)}


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("윈도우 캐시...", flush=True)
    src = {
        "WEDA": cache_windows(weda.iter_dataset(DATA / "WEDA_raw"), weda.FS),
        "UMAFall": cache_windows(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS),
        "SmartFallMM": cache_windows(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS),
    }
    eld = [t for t in cache_windows(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS) if t[1] == 0]
    report = {}
    for clf_name in ("RF", "ExtraTrees"):
        for ext in (False, True):
            key = f"{clf_name}_{'base+extra' if ext else 'base'}"
            report[key] = lodo_fp(src, eld, ext, clf_name)
            print(f"  {key:22s} LODO F1={report[key]['lodo_f1']:.3f} "
                  f"sens={report[key]['lodo_sens']:.3f} 고령FP={report[key]['elderly_fp']:.3f}", flush=True)
    (ROOT / "artifacts" / "wrist_features_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    base = report["RF_base"]["lodo_f1"]; bestk = max(report, key=lambda k: report[k]["lodo_f1"])
    print(f"\n최고={bestk} F1={report[bestk]['lodo_f1']:.3f} (RF_base {base:.3f}, Δ{report[bestk]['lodo_f1']-base:+.3f})")
    print("[saved] artifacts/wrist_features_report.json")


if __name__ == "__main__":
    main()
