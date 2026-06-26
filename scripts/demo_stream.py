"""내러티브 데모 — 독거 고령자의 하루를 시뮬레이션하며 판단 출력.

시나리오: 정상 아침 → 산책(운동) → 휴식 → 낙상+무활동 → (자동통화).
중간에 운동 중 고심박(정상 빈맥)이 '오경보로 새지 않는지'도 확인.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.pipeline import StreamProcessor
from widu.types import HRSample, IMUSample, Accuracy, AlertLevel
from widu.datasets import synthetic

rng = np.random.default_rng(7)


def clock(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def show(tag, a):
    if a is None:
        return
    icon = {"NORMAL": "🟢", "INFO": "🔵", "CAUTION": "🟡",
            "EMERGENCY": "🔴", "NO_CONTACT": "⚪"}[a.level.value]
    print(f"{clock(a.ts)} {icon} [{a.level.value:9s}] {a.reason_ko or '안정'}"
          f"  → {a.escalation}   ({tag})")


def feed_hr(sp, u, t0, n, bpm, ctx_imu=None):
    last = None
    for i in range(n):
        t = t0 + i
        if ctx_imu is not None:  # 동반 IMU(활동맥락)
            for k in range(25):
                sp.ingest_imu(u, IMUSample(t + k / 25.0, *ctx_imu))
        last = sp.ingest_hr(u, HRSample(float(t), bpm + rng.normal(0, 2), Accuracy.HIGH))
    return last


def main():
    sp = StreamProcessor()
    u = "한복순(82)"
    base = datetime(2026, 6, 24, 7, 0, 0).timestamp()
    sp.set_safe_zones(u, [(37.55, 127.0, 100.0)])

    print("=== WidU 데모: 독거 고령자의 하루 ===\n")

    # 07:00 기상·아침 휴식 (기준선 학습)
    a = feed_hr(sp, u, base, 600, 70, ctx_imu=(0.02, 0.0, 1.0))
    show("아침 휴식", a)

    # 09:00 산책 — 활동맥락에서 고심박(정상 빈맥) → 오경보 아니어야
    t = base + 7200
    a = feed_hr(sp, u, t, 300, 128, ctx_imu=(0.5, 0.3, 1.1))
    show("산책 중(고심박이지만 운동맥락)", a)

    # 12:00 점심 후 휴식
    t = base + 18000
    a = feed_hr(sp, u, t, 300, 72, ctx_imu=(0.02, 0.0, 1.0))
    show("점심 후 휴식", a)

    # 15:00 낙상 발생
    t = base + 28800
    print(f"\n  ...{clock(t)} 낙상 발생...")
    last = None
    for s in synthetic.imu_fall_sequence(t0=t, seed=3):
        o = sp.ingest_imu(u, s)
        if o and o.level == AlertLevel.EMERGENCY:
            last = o
    show("낙상 후 무활동", last)

    print("\n=== 요약: 운동 고심박은 억제, 낙상은 위급·자동통화 ===")


if __name__ == "__main__":
    main()
