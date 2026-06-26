"""WEDA-FALL 로더 — 손목 스마트워치(Fitbit Sense) · 고령자 · 50Hz.

우리 실제 기기(손목)와 정확히 일치하는 유일한 공개셋. 낙상유형 F05~F08 =
'앉다가/실신으로 넘어짐'(고령 소프트폴) 포함 → L2가 고전한 케이스의 실데이터.
출처: github.com/joaojtmarques/WEDA-FALL
구조: dataset/50Hz/{D01..,F01..F08}/U##_R##_{accel,gyro,orientation}.csv
단위: accel=m/s²(→g), gyro=rad/s. 타임스탬프 불규칙 → 50Hz 균일 그리드 보간.
반환 (N,6): [ax,ay,az(g), gx,gy,gz(rad/s)] — WidU 표준 IMU 계약.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Tuple

import numpy as np

FS = 50.0
GRAV = 9.81


def _interp_to_grid(t: np.ndarray, xyz: np.ndarray, grid: np.ndarray) -> np.ndarray:
    return np.column_stack([np.interp(grid, t, xyz[:, c]) for c in range(3)])


def load_trial(accel_csv: Path) -> Tuple[np.ndarray, int, str, str]:
    accel_csv = Path(accel_csv)
    gyro_csv = Path(str(accel_csv).replace("_accel.csv", "_gyro.csv"))

    def _read(p):
        d = np.genfromtxt(p, delimiter=",", skip_header=1)  # 위치기반: time,x,y,z
        if d.ndim == 1:
            d = d.reshape(1, -1)
        d = d[~np.isnan(d).any(axis=1)]
        return d

    a = _read(accel_csv)
    if len(a) < 4 or a.shape[1] < 4:
        return np.zeros((0, 6)), _label(accel_csv), _subj(accel_csv), _ftype(accel_csv)
    ta = a[:, 0].astype(float)
    axyz = a[:, 1:4] / GRAV
    if gyro_csv.exists():
        g = _read(gyro_csv)
        if len(g) >= 2 and g.shape[1] >= 4:
            tg, gxyz = g[:, 0].astype(float), g[:, 1:4]
        else:
            tg, gxyz = ta, np.zeros_like(axyz)
    else:
        tg, gxyz = ta, np.zeros_like(axyz)
    dur = max(ta[-1] - ta[0], (tg[-1] - tg[0]) if len(tg) else 0.0)
    if dur <= 0 or len(ta) < 4:
        return np.zeros((0, 6)), _label(accel_csv), _subj(accel_csv), _ftype(accel_csv)
    grid = np.arange(0.0, dur, 1.0 / FS)
    acc = _interp_to_grid(ta - ta[0], axyz, grid)
    gyr = _interp_to_grid(tg - tg[0], gxyz, grid) if len(tg) >= 2 else np.zeros((len(grid), 3))
    arr = np.column_stack([acc, gyr])
    return arr, _label(accel_csv), _subj(accel_csv), _ftype(accel_csv)


def _ftype(p: Path) -> str:
    return p.parent.name            # D01.. / F01..F08

def _label(p: Path) -> int:
    return 1 if p.parent.name.upper().startswith("F") else 0

def _subj(p: Path) -> str:
    return p.name.split("_")[0]     # U01..


def iter_dataset(root: Path, fs_dir: str = "50Hz") -> Iterator[Tuple[np.ndarray, int, str, str]]:
    base = Path(root)
    d50 = base / "dataset" / fs_dir
    if not d50.exists():
        cand = list(base.rglob(fs_dir))
        d50 = cand[0] if cand else base
    for f in sorted(d50.rglob("*_accel.csv")):
        arr, lab, subj, ft = load_trial(f)
        if len(arr) == 0:
            continue
        yield arr, lab, subj, ft


SOFT_FALL_TYPES = {"F05", "F06", "F07", "F08"}   # 앉다가/실신 = 고령 소프트폴
