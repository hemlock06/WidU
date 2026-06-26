"""활동맥락 임계 보정 — 손목 ACC SMA → {REST/LOW/ACTIVE} 임계를 PPG-DaLiA 라벨로 최적화.

L1 오탐의 주원인 = 활동 오추정(0.68). SMA 임계가 E4 손목 ACC에 안 맞을 수 있음.
라벨(휴식/저활동/운동) 대비 3-class 일치를 최대화하는 SMA_REST/SMA_LOW 를 그리드 탐색.
출력: 권장 임계 + 보정 전/후 일치도. (config 갱신은 사람이 판단)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import Activity
from widu.datasets import ppg_dalia

ACC_FS = 32.0
HR_DT = 2.0


def collect(root):
    SMA, TRUE = [], []
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        n = len(hr)
        act_fs = len(act) / (n * HR_DT) if len(act) else 0
        for i in range(n):
            s = int(i * HR_DT * ACC_FS)
            win = acc[s:s + int(HR_DT * ACC_FS)]
            if len(win) < 8 or not len(act):
                continue
            smv = np.sqrt((win ** 2).sum(1))
            SMA.append(float(np.abs(smv - 1.0).mean()))
            ai = min(len(act) - 1, int(i * HR_DT * act_fs))
            TRUE.append(ppg_dalia.activity_to_context(act[ai]))
    return np.array(SMA), np.array(TRUE)


def agree(sma, true, rest_th, low_th):
    pred = np.where(sma < rest_th, "REST", np.where(sma < low_th, "LOW", "ACTIVE"))
    # 3-class + 휴식/운동 이분 일치
    three = (pred == true).mean()
    rest_bin = ((pred == "REST") == (true == "REST")).mean()
    return three, rest_bin


def main():
    root = ROOT / "data" / "PPG_DaLiA"
    if not (root.exists() and any(root.rglob("S*.pkl"))):
        print("PPG-DaLiA 미발견."); return
    sma, true = collect(root)
    print(f"표본 {len(sma)}, SMA 분포 p25/50/75 = {np.percentile(sma,[25,50,75]).round(3)}")
    print(f"라벨 분포 REST {np.mean(true=='REST'):.2f} LOW {np.mean(true=='LOW'):.2f} ACTIVE {np.mean(true=='ACTIVE'):.2f}")

    base3, baseb = agree(sma, true, Activity.SMA_REST, Activity.SMA_LOW)
    print(f"[기존 {Activity.SMA_REST}/{Activity.SMA_LOW}] 3-class {base3:.3f} 휴식이분 {baseb:.3f}")

    best = (base3, Activity.SMA_REST, Activity.SMA_LOW)
    for r in np.linspace(0.02, 0.30, 29):
        for l in np.linspace(r + 0.02, 0.8, 30):
            t3, _ = agree(sma, true, r, l)
            if t3 > best[0]:
                best = (t3, round(float(r), 3), round(float(l), 3))
    t3, tb = agree(sma, true, best[1], best[2])
    print(f"[보정 {best[1]}/{best[2]}] 3-class {t3:.3f} 휴식이분 {tb:.3f}  (개선 {t3-base3:+.3f})")
    print(f"\n권장: Activity.SMA_REST={best[1]}, SMA_LOW={best[2]}  (config.py 갱신)")
    if t3 - base3 < 0.02:
        print("⚠ 개선 미미 — 손목 ACC 본질적 한계(손동작≠활동). 임계만으론 한계.")


if __name__ == "__main__":
    main()
