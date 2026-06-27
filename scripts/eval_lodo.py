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

from widu.config import L2
from widu.eval.metrics import binary_metrics
from widu.falleval import (cache_windows, feats, rf, DATA,
                           src_sisfall, src_weda, src_uma, src_smm, FS)   # 공유 헬퍼(DRY)


def _windows(trials, src_fs):
    """(arr,lab,subj) 제너레이터 → (X feats, y, groups). cache_windows+feats 와 동일."""
    w = cache_windows(trials, src_fs)
    return (feats([x for x, _, _ in w]),
            np.array([l for _, l, _ in w]),
            np.array([s for _, _, s in w]))


def build_sources(position: str) -> dict:
    print(f"\n[{position}] 특징 추출 중...", flush=True)
    if position == "wrist":
        specs = {
            "WEDA":        (src_weda(), FS["weda"]),
            "UMAFall":     (src_uma("WRIST"), FS["uma"]),
            "SmartFallMM": (src_smm("young", "watch"), FS["smm"]),
        }
    else:  # waist
        specs = {
            "SisFall":     (src_sisfall(), FS["sisfall"]),
            "UMAFall":     (src_uma("WAIST"), FS["uma"]),
            "SmartFallMM": (src_smm("young", "phone"), FS["smm"]),
        }
    out = {}
    for name, (gen, fs) in specs.items():
        X, y, g = _windows(gen, fs)
        out[name] = (X, y, g)
        print(f"  {name}: {len(y)} windows (낙상 {int(y.sum())}/ADL {int((y==0).sum())}), "
              f"피험자 {len(set(g))}", flush=True)
    return out


def lodo(sources: dict, th: float) -> dict:
    names = list(sources)
    rows = {}
    sens_l, prec_l, f1_l = [], [], []
    for held in names:
        Xtr = np.vstack([sources[n][0] for n in names if n != held])
        ytr = np.concatenate([sources[n][1] for n in names if n != held])
        Xte, yte, _ = sources[held]
        clf = rf().fit(Xtr, ytr)
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
    clf = rf().fit(Xtr, ytr)

    def fp_rate(gen, fs):
        X, y, _ = _windows(gen, fs)
        adl = X[y == 0]
        if len(adl) == 0:
            return None, 0
        pred = (clf.predict_proba(adl)[:, 1] >= th).astype(int)
        return round(float(pred.mean()), 3), len(adl)

    young_fp, ny = fp_rate(src_smm("young", "watch"), FS["smm"])   # in-dist ADL(참고)
    old_fp, no = fp_rate(src_smm("old", "watch"), FS["smm"])        # 고령 ADL
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
