"""L1 지속시간 최적화 — 속도 vs 오탐 트레이드오프.

지속시간↑ = 오탐↓ 이지만 알림 지연↑(응급엔 느림).
→ 최선 = '오탐을 0(또는 허용)으로 유지하는 가장 짧은 지속시간'(가장 빠른 알림).
rest_only=True 고정, 지속시간 스윕. PPG-DaLiA(건강자→모든경보=오탐).
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


def fp(hr, ctxs, sustain):
    m = PersonalHRModel(sustain_sec=sustain, rest_only=True)
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
    durs = [60, 90, 120, 150, 180, 240, 300, 600]
    tot_h = 0.0
    data = []
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        n = len(hr); ctxs = []
        for i in range(n):
            s = int(i * HR_DT * ACC_FS); win = acc[s:s + int(HR_DT * ACC_FS)]
            ctxs.append(acc_ctx(win) if len(win) >= 8 else "UNKNOWN")
        data.append((hr, ctxs)); tot_h += n * HR_DT / 3600.0
    totals = {d: sum(fp(hr, ctxs, d) for hr, ctxs in data) for d in durs}
    print(f"\n=== L1 지속시간 스윕 (rest_only, 건강 15명, {tot_h:.0f}h) ===")
    best0 = None
    for d in durs:
        r = totals[d] / tot_h
        if r == 0 and best0 is None:
            best0 = d
        print(f"  {d:4d}s ({d/60:.1f}분)  오탐 {r:6.2f}/시간   알림지연 ~{d/60:.1f}분")
    print(f"\n→ 오탐 0 최단 지속 = {best0}s ({best0/60:.0f}분) = 최선(가장 빠른 알림)" if best0 else "\n→ 측정 구간 내 오탐 0 없음")
    print(f"   사용자 제안 3분(180s) 오탐/시간 = {totals[180]/tot_h:.2f}")


if __name__ == "__main__":
    main()
