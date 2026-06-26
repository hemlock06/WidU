"""SmartFallMM 로더 — Texas State, 손목(스마트워치)+엉덩이, 젊은층+고령(65.5세).

LODO(leave-one-dataset-out) 보강 + 고령 ADL 오탐 probe용.
 - young: 활동 1~9=ADL, 10~14=낙상(back/front/left/right/rotate) → 손목·허리 3번째 소스.
 - old: 활동 1~8=ADL만(낙상 없음) → 고령 일상동작에 낙상분류기가 오발하는지 테스트.
출처: github.com/txst-cs-smartfall/SmartFallMM-Dataset
구조: {young,old}/{accelerometer,gyroscope}/{watch,phone,meta_wrist,meta_hip}/S##A##T##.csv
포맷: 헤더없음 [timestamp, x, y, z]. accel=m/s²(→g), gyro=rad/s. 타임스탬프 불규칙→50Hz 보간.
반환 (N,6): [ax,ay,az(g), gx,gy,gz(rad/s)] — WidU 표준 IMU 계약(WEDA와 동일).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, Tuple

import numpy as np
import pandas as pd

FS = 50.0
GRAV = 9.81
_NAME = re.compile(r"S(\d+)A(\d+)T(\d+)", re.IGNORECASE)
FALL_ACTS = {10, 11, 12, 13, 14}   # back/front/left/right/rotate fall (young만)


def _parse_name(p: Path) -> Tuple[str, int, int]:
    m = _NAME.search(p.name)
    if not m:
        return p.stem, -1, -1
    return f"S{int(m.group(1)):02d}", int(m.group(2)), int(m.group(3))


def _read_ts_xyz(p: Path) -> Tuple[np.ndarray, np.ndarray]:
    """[t_sec(상대), xyz(N,3)]. datetime 타임스탬프 → 초."""
    df = pd.read_csv(p, header=None, names=["t", "x", "y", "z"])
    if len(df) < 2:
        return np.empty(0), np.empty((0, 3))
    t = pd.to_datetime(df["t"], errors="coerce", format="%Y-%m-%d %H:%M:%S.%f")
    # 일부 파일에 손상값('0.008547778.1' 등) 존재 → 숫자 강제변환 후 결측 행 제거
    xyz = np.column_stack([pd.to_numeric(df[c], errors="coerce").to_numpy(float)
                           for c in ("x", "y", "z")])
    ok = t.notna().to_numpy() & ~np.isnan(xyz).any(axis=1)
    t, xyz = t[ok], xyz[ok]
    if len(t) < 2:
        return np.empty(0), np.empty((0, 3))
    ts = (t - t.iloc[0]).dt.total_seconds().to_numpy()
    # 단조 증가 보장(중복/역전 ts 제거)
    keep = np.concatenate([[True], np.diff(ts) > 0])
    return ts[keep], xyz[keep]


def _interp(t: np.ndarray, xyz: np.ndarray, grid: np.ndarray) -> np.ndarray:
    return np.column_stack([np.interp(grid, t, xyz[:, c]) for c in range(3)])


def load_trial(accel_csv: Path, group: str, position: str) -> Tuple[np.ndarray, int, str, int]:
    subj, act, _ = _parse_name(accel_csv)
    gyro_csv = Path(accel_csv).parents[2] / "gyroscope" / position / accel_csv.name
    ta, axyz = _read_ts_xyz(accel_csv)
    if len(ta) < 4:
        return np.zeros((0, 6)), -1, subj, act
    axyz = axyz / GRAV
    if gyro_csv.exists():
        tg, gxyz = _read_ts_xyz(gyro_csv)
    else:
        tg, gxyz = np.empty(0), np.empty((0, 3))
    dur = ta[-1] - ta[0]
    if dur <= 0:
        return np.zeros((0, 6)), -1, subj, act
    grid = np.arange(0.0, dur, 1.0 / FS)
    acc = _interp(ta - ta[0], axyz, grid)
    gyr = _interp(tg - tg[0], gxyz, grid) if len(tg) >= 2 else np.zeros((len(grid), 3))
    arr = np.column_stack([acc, gyr])
    label = 1 if act in FALL_ACTS else 0
    return arr, label, subj, act


def iter_dataset(root: Path, group: str = "young", position: str = "watch"
                 ) -> Iterator[Tuple[np.ndarray, int, str, int]]:
    """group∈{young,old}, position∈{watch,phone,meta_wrist,meta_hip}."""
    base = Path(root) / group / "accelerometer" / position
    if not base.exists():
        return
    for f in sorted(base.glob("*.csv")):
        arr, lab, subj, act = load_trial(f, group, position)
        if len(arr) == 0:
            continue
        yield arr, lab, subj, act
