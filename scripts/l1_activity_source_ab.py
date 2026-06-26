"""L1 활동 소스 A/B — raw ACC 추정 vs '정확한 활동상태'(OS 활동인식 대리=라벨).

질문: 활동맥락을 raw 손목 ACC 로 추측하지 말고 OS 활동인식(CMMotionActivity/
Activity Recognition API)에서 받아오면 헛알람이 얼마나 주나?
PPG-DaLiA 활동 라벨 = '정확한 활동상태'의 대리(OS가 센서융합으로 주는 값에 해당).
건강 피험자 → 모든 경보=오탐. ACC맥락 vs 라벨맥락으로 같은 L1 돌려 FP/시간 비교.
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
    smv = np.sqrt((win ** 2).sum(1)); sma = float(np.abs(smv - 1.0).mean())
    return "REST" if sma < Activity.SMA_REST else ("LOW" if sma < Activity.SMA_LOW else "ACTIVE")


def fp_episodes(hr, ctxs):
    model = PersonalHRModel(); eps = 0; prev = False
    for i, (v, c) in enumerate(zip(hr, ctxs)):
        d = model.update(HRSample(i * HR_DT, float(v), Accuracy.HIGH), ActivityContext(c))
        al = d is not None and d.level in (AlertLevel.CAUTION, AlertLevel.EMERGENCY)
        if al and not prev:
            eps += 1
        prev = al
    return eps


def main():
    root = ROOT / "data" / "PPG_DaLiA"
    if not (root.exists() and any(root.rglob("S*.pkl"))):
        print("PPG-DaLiA 미발견."); return
    acc_fp = lab_fp = tot_h = 0.0
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        n = len(hr)
        afs = len(act) / (n * HR_DT) if len(act) else 0
        ctx_acc, ctx_lab = [], []
        for i in range(n):
            s = int(i * HR_DT * ACC_FS); win = acc[s:s + int(HR_DT * ACC_FS)]
            ctx_acc.append(acc_ctx(win) if len(win) >= 8 else "UNKNOWN")
            ai = min(len(act) - 1, int(i * HR_DT * afs)) if len(act) else 0
            ctx_lab.append(ppg_dalia.activity_to_context(act[ai]) if len(act) else "UNKNOWN")
        acc_fp += fp_episodes(hr, ctx_acc)
        lab_fp += fp_episodes(hr, ctx_lab)
        tot_h += n * HR_DT / 3600.0
    print(f"\n=== L1 활동소스 A/B (건강 15명, {tot_h:.0f}h) ===")
    print(f"  raw ACC 추정         오탐 {acc_fp/tot_h:.2f}/시간 (총 {int(acc_fp)})")
    print(f"  정확한 활동상태(OS)  오탐 {lab_fp/tot_h:.2f}/시간 (총 {int(lab_fp)})")
    red = (1 - lab_fp / acc_fp) * 100 if acc_fp else 0
    print(f"  → OS 활동상태 사용 시 오탐 {red:.0f}% 감소")


if __name__ == "__main__":
    main()
