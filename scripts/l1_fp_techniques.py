"""L1 오탐 억제 기법 스윕 — 검증된 기법을 PPG-DaLiA로 실측.

기법(웹리서치 근거):
  - 긴 지속시간(애플 HR 알림=10분, ICU 시간지연 50~67%↓)
  - 안정시에만(Stanford/애플 '비활동 시'): 활동 중 심박 무시 → 활동오류 오탐 제거
건강 피험자 → 모든 경보=오탐. 조합별 FP/시간 비교.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import Activity
from widu.types import HRSample, ActivityContext, Accuracy, AlertLevel
from widu.l1_hr import PersonalHRModel
from widu.datasets import ppg_dalia

ACC_FS, HR_DT = 32.0, 2.0


def acc_ctx(win):
    sma = float(np.abs(np.sqrt((win ** 2).sum(1)) - 1.0).mean())
    return "REST" if sma < Activity.SMA_REST else ("LOW" if sma < Activity.SMA_LOW else "ACTIVE")


def fp(hr, ctxs, sustain, rest_only):
    m = PersonalHRModel(sustain_sec=sustain, rest_only=rest_only)
    eps = 0; prev = False
    for i, (v, c) in enumerate(zip(hr, ctxs)):
        d = m.update(HRSample(i * HR_DT, float(v), Accuracy.HIGH), ActivityContext(c))
        al = d is not None and d.level in (AlertLevel.CAUTION, AlertLevel.EMERGENCY)
        if al and not prev:
            eps += 1
        prev = al
    return eps


def main():
    root = ROOT / "data" / "PPG_DaLiA"
    if not (root.exists() and any(root.rglob("S*.pkl"))):
        print("PPG-DaLiA 미발견."); return
    configs = {
        "A 현재(20s, 전체)":        (20, False),
        "B +긴지속(300s, 전체)":     (300, False),
        "C +안정시만(20s, rest)":    (20, True),
        "D 둘다(300s, rest)":        (300, True),
    }
    totals = {k: 0 for k in configs}
    tot_h = 0.0; rest_frac = []
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        n = len(hr)
        ctxs = []
        for i in range(n):
            s = int(i * HR_DT * ACC_FS); win = acc[s:s + int(HR_DT * ACC_FS)]
            ctxs.append(acc_ctx(win) if len(win) >= 8 else "UNKNOWN")
        rest_frac.append(np.mean([c == "REST" for c in ctxs]))
        for k, (sus, ro) in configs.items():
            totals[k] += fp(hr, ctxs, sus, ro)
        tot_h += n * HR_DT / 3600.0
    print(f"\n=== L1 오탐 억제 기법 스윕 (건강 15명, {tot_h:.0f}h, 안정구간 {np.mean(rest_frac)*100:.0f}%) ===")
    base = totals["A 현재(20s, 전체)"] / tot_h
    for k in configs:
        r = totals[k] / tot_h
        red = (1 - r / base) * 100 if base else 0
        print(f"  {k:22s} 오탐 {r:5.2f}/시간 (총 {totals[k]:3d})  {('기준' if k.startswith('A') else f'{red:+.0f}%')}")


if __name__ == "__main__":
    main()
