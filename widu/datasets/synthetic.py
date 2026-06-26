"""합성 신호 생성 — 공개 데이터 없이도 탐지기 견고성 스트레스 테스트.

실제 검증은 SisFall/PPG-DaLiA/VitalDB 가 담당하고, 여기서는
'주입된 이상'으로 파이프라인의 반응을 빠르게 확인한다.
"""
from __future__ import annotations

import math
import random
from typing import List, Tuple

import numpy as np

from ..types import HRSample, IMUSample, Accuracy


def hr_stream(
    n: int = 3600,
    base: float = 72.0,
    fs: float = 1.0,
    anomalies: List[Tuple[int, int, float]] = None,
    t0: float = 0.0,
    seed: int = 0,
) -> Tuple[List[HRSample], np.ndarray]:
    """심박 스트림 + 라벨(0 정상 / 1 이상) 반환.

    anomalies: [(start_idx, end_idx, target_bpm), ...]
    """
    rng = random.Random(seed)
    anomalies = anomalies or []
    samples, labels = [], np.zeros(n, dtype=int)
    # 일주기성(낮 높고 밤 낮음) + 노이즈
    for i in range(n):
        circ = 6 * math.sin(2 * math.pi * (i / n))
        bpm = base + circ + rng.gauss(0, 2.5)
        lab = 0
        for (s, e, tgt) in anomalies:
            if s <= i < e:
                bpm = tgt + rng.gauss(0, 2.0)
                lab = 1
        samples.append(HRSample(t0 + i / fs, max(25.0, bpm), Accuracy.HIGH))
        labels[i] = lab
    return samples, labels


def adl_window(fs: float = 50.0, win_sec: float = 2.0, seed: int = 0) -> np.ndarray:
    """일상활동(낙상 아님) 윈도우 (N,6). 걷기/앉기 수준의 진동."""
    rng = np.random.default_rng(seed)
    n = int(fs * win_sec)
    t = np.arange(n) / fs
    # 보행 진동 ~2Hz
    ax = 0.15 * np.sin(2 * math.pi * 2 * t) + rng.normal(0, 0.05, n)
    ay = 0.10 * np.cos(2 * math.pi * 2 * t) + rng.normal(0, 0.05, n)
    az = 1.0 + 0.15 * np.sin(2 * math.pi * 2 * t) + rng.normal(0, 0.05, n)
    g = rng.normal(0, 0.3, (n, 3))
    return np.column_stack([ax, ay, az, g])


def fall_window(fs: float = 50.0, win_sec: float = 2.0, seed: int = 0) -> np.ndarray:
    """낙상 윈도우 (N,6): 자유낙하→충격→정지 자세변화."""
    rng = np.random.default_rng(seed)
    n = int(fs * win_sec)
    acc = np.ones((n, 3)) * np.array([0, 0, 1.0])
    half = n // 2
    # 자유낙하(0g 근처) 0.3s
    ff = int(0.3 * fs)
    acc[half - ff:half] = rng.normal(0.1, 0.05, (ff, 3))
    # 충격 스파이크
    acc[half] = np.array([2.6, 1.9, 2.4]) + rng.normal(0, 0.2, 3)
    acc[half + 1] = np.array([1.5, 1.2, 1.4])
    # 충격 후 누운 자세(중력축 변경) + 정지
    acc[half + 2:] = np.array([0.9, 0.2, 0.1]) + rng.normal(0, 0.03, (n - half - 2, 3))
    gyro = rng.normal(0, 0.2, (n, 3))
    gyro[half - ff:half + 3] += rng.normal(0, 3.0, (ff + 3, 3))  # 회전 급변
    return np.column_stack([acc, gyro])


def imu_fall_sequence(t0: float = 0.0, fs: float = 50.0, seed: int = 0):
    """파이프라인 입력용: 정지→자유낙하→충격→장기 무활동 IMUSample 리스트."""
    rng = np.random.default_rng(seed)
    out, t, dt = [], t0, 1.0 / fs
    for _ in range(int(2.4 * fs)):           # 프리필 정지
        out.append(IMUSample(t, *rng.normal([0, 0, 1.0], 0.02), *rng.normal(0, 0.05, 3))); t += dt
    for _ in range(int(0.3 * fs)):           # 자유낙하
        out.append(IMUSample(t, *rng.normal([0.05, 0.05, 0.15], 0.03), *rng.normal(0, 0.1, 3))); t += dt
    out.append(IMUSample(t, 2.6, 1.9, 2.4, 5, 4, 3)); t += dt   # 충격
    for _ in range(int(10 * fs)):            # 무활동 10s
        out.append(IMUSample(t, *rng.normal([0.9, 0.1, 0.2], 0.01), *rng.normal(0, 0.05, 3))); t += dt
    return out
