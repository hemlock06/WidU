"""LODO(Leave-One-Dataset-Out) 낙상 일반화 검증 + 고령 ADL 오탐 probe.

비판원칙: '양' 아니라 '처음 보는 분포에 일반화되나'가 정직한 척도.
 위치별로 데이터셋 3개 중 1개를 통째로 빼고(held-out) 나머지로 학습 → 빼둔 셋 테스트.
 평균 = 새 출처(미지 기기/코호트)로의 기대 일반화. in-domain CV와의 격차 = '새 출처 페널티'.

 손목: WEDA · UMAFall(wrist) · SmartFallMM(young/watch)
 허리: SisFall · UMAFall(waist) · SmartFallMM(young/phone)

고령 probe: 손목 모델 → SmartFallMM old/watch(고령 ADL, 낙상無)의 오탐율 vs young ADL.
 (고령은 ADL만 → 낙상 recall 갭은 못 닫고, '고령 일상에 오발하는지'만 측정.)

산출 → artifacts/lodo_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import RandomForestClassifier

from widu.config import L2
from widu.preprocess import resample_antialiased, extract_window
from widu.l2_fall import extract_features
from widu.eval.metrics import binary_metrics
from widu.datasets import sisfall, weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)


def _windows(trials, src_fs):
    """(arr, label, subj) 제너레이터 → (X feats, y, groups)."""
    X, y, g = [], [], []
    for arr, lab, subj in trials:
        if lab < 0 or len(arr) < 4:
            continue
        a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
        win = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < MIN_WIN:
            continue
        X.append(extract_features(np.asarray(win, float), L2.FS))
        y.append(int(lab)); g.append(subj)
    return np.array(X), np.array(y), np.array(g)


def _sisfall():
    for arr, lab, meta in sisfall.iter_dataset(DATA / "SisFall"):
        yield arr, lab, f"SIS_{meta}"

def _weda():
    for arr, lab, subj, ft in weda.iter_dataset(DATA / "WEDA_raw"):
        yield arr, lab, f"WEDA_{subj}"

def _uma(pos):
    for arr, lab, subj, age in umafall.iter_dataset(DATA / "UMAFall_raw", pos):
        yield arr, lab, f"UMA_{subj}"

def _smm(group, pos):
    for arr, lab, subj, act in smm.iter_dataset(DATA / "SmartFallMM", group, pos):
        yield arr, lab, f"SMM_{subj}"


def build_sources(position: str) -> dict:
    print(f"\n[{position}] 특징 추출 중...", flush=True)
    if position == "wrist":
        specs = {
            "WEDA":        (_weda(), weda.FS),
            "UMAFall":     (_uma("WRIST"), umafall.FS),
            "SmartFallMM": (_smm("young", "watch"), smm.FS),
        }
    else:  # waist
        specs = {
            "SisFall":     (_sisfall(), sisfall.FS),
            "UMAFall":     (_uma("WAIST"), umafall.FS),
            "SmartFallMM": (_smm("young", "phone"), smm.FS),
        }
    out = {}
    for name, (gen, fs) in specs.items():
        X, y, g = _windows(gen, fs)
        out[name] = (X, y, g)
        print(f"  {name}: {len(y)} windows (낙상 {int(y.sum())}/ADL {int((y==0).sum())}), "
              f"피험자 {len(set(g))}", flush=True)
    return out


def _rf():
    return RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                  random_state=0, n_jobs=-1)


def lodo(sources: dict, th: float) -> dict:
    names = list(sources)
    rows = {}
    sens_l, prec_l, f1_l = [], [], []
    for held in names:
        Xtr = np.vstack([sources[n][0] for n in names if n != held])
        ytr = np.concatenate([sources[n][1] for n in names if n != held])
        Xte, yte, _ = sources[held]
        clf = _rf().fit(Xtr, ytr)
        proba = clf.predict_proba(Xte)[:, 1]
        pred = (proba >= th).astype(int)
        m = binary_metrics(yte, pred)
        d = m.summary() if hasattr(m, "summary") else m
        rows[held] = {k: round(float(d[k]), 3) for k in ("sensitivity", "precision", "f1")
                      if k in d}
        sens_l.append(rows[held].get("sensitivity", 0))
        prec_l.append(rows[held].get("precision", 0))
        f1_l.append(rows[held].get("f1", 0))
        print(f"  held-out={held}: {rows[held]}", flush=True)
    rows["MEAN(novel-source 기대)"] = {
        "sensitivity": round(float(np.mean(sens_l)), 3),
        "precision": round(float(np.mean(prec_l)), 3),
        "f1": round(float(np.mean(f1_l)), 3),
    }
    return rows


def elderly_fp_probe(wrist_sources: dict, th: float) -> dict:
    """젊은 손목 전 데이터 학습 → 고령 ADL vs 젊은 ADL 오탐율."""
    Xtr = np.vstack([wrist_sources[n][0] for n in wrist_sources])
    ytr = np.concatenate([wrist_sources[n][1] for n in wrist_sources])
    clf = _rf().fit(Xtr, ytr)

    def fp_rate(gen, fs):
        X, y, _ = _windows(gen, fs)
        adl = X[y == 0]
        if len(adl) == 0:
            return None, 0
        pred = (clf.predict_proba(adl)[:, 1] >= th).astype(int)
        return round(float(pred.mean()), 3), len(adl)

    young_fp, ny = fp_rate(_smm("young", "watch"), smm.FS)   # in-dist ADL(참고)
    old_fp, no = fp_rate(_smm("old", "watch"), smm.FS)        # 고령 ADL
    return {
        "young_adl_fp_rate": young_fp, "young_adl_n": ny,
        "old_adl_fp_rate": old_fp, "old_adl_n": no,
        "note": "고령은 ADL만 수행 → 낙상 recall 갭은 미측정. 오발경향만. "
                "young은 학습에 포함(낙관적 참고치), old는 완전 미지(정직치).",
    }


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    th = L2.FALL_PROBA_TH
    report = {"threshold": th}
    for pos in ("wrist", "waist"):
        src = build_sources(pos)
        print(f"\n=== LODO [{pos}] (th={th}) ===", flush=True)
        report[pos] = lodo(src, th)
        if pos == "wrist":
            print("\n=== 고령 ADL 오탐 probe ===", flush=True)
            report["elderly_fp_probe"] = elderly_fp_probe(src, th)
            print(json.dumps(report["elderly_fp_probe"], ensure_ascii=False, indent=2))
    out = ROOT / "artifacts" / "lodo_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")
    print(json.dumps({k: report[k] for k in report if k in ("wrist", "waist")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
