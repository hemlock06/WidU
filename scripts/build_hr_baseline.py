"""개인화 HR 베이스라인(L1) 구축 데모.

PPG-DaLiA(있으면)로 '활동맥락별 정상 심박' 개인 기준선을 학습하고 출력.
없으면 합성으로 시연. 이것이 L1 개인화의 핵심(맥락조건부 기준선)을 실증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.l1_hr import PersonalHRModel
from widu.types import HRSample, ActivityContext, Accuracy
from widu.datasets import ppg_dalia


def from_ppg_dalia(root: Path):
    out = []
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        model = PersonalHRModel()
        m = min(len(hr), len(act))
        for i in range(m):
            ctx = ppg_dalia.activity_to_context(act[i] if len(act) else 0)
            ts = float(i * 2)  # 라벨 2초 간격
            model.update(HRSample(ts, float(hr[i]), Accuracy.HIGH),
                         ActivityContext(ctx))
        rows = {c: model.baseline(ActivityContext(c)) for c in ("REST", "LOW", "ACTIVE")}
        out.append((subj, rows))
    return out


def from_synthetic():
    model = PersonalHRModel()
    rng = np.random.default_rng(0)
    base = {"REST": 68, "LOW": 85, "ACTIVE": 115}
    t = 0.0
    for _ in range(2000):
        for ctx, b in base.items():
            model.update(HRSample(t, b + rng.normal(0, 6), Accuracy.HIGH),
                         ActivityContext(ctx))
            t += 1
    return [("synthetic", {c: model.baseline(ActivityContext(c)) for c in base})]


def main():
    root = ROOT / "data" / "PPG_DaLiA"
    if root.exists() and any(root.rglob("S*.pkl")):
        print(f"[baseline] PPG-DaLiA 사용: {root}")
        results = from_ppg_dalia(root)
    else:
        print("[baseline] PPG-DaLiA 미발견 → 합성 시연 (실데이터: scripts/download_data.py --ppgdalia)")
        results = from_synthetic()

    for subj, rows in results:
        print(f"\n[{subj}] 맥락별 학습된 정상 심박 기준선(mean±std, n)")
        for ctx, (mean, std, n) in rows.items():
            print(f"  {ctx:7s}: {mean:5.1f} ± {std:4.1f}  (n={n})")
    print("\n→ 같은 bpm도 맥락에 따라 정상/이상 판정이 달라진다(L1 핵심).")


if __name__ == "__main__":
    main()
