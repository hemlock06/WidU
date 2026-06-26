"""UMAFall 로더 — 다부위(손목·허리·가슴·발목·폰), cross-dataset 일반화용.

출처: figshare 4214283 (Universidad de Malaga), 19명(14~68세), 낙상+ADL.
한 CSV 안에 5개 위치가 섞여 있고 SensorID/Type 으로 구분.
  SensorID: 0=RIGHTPOCKET(폰), 1=CHEST, 2=WAIST, 3=WRIST, 4=ANKLE
  SensorType: 0=Accel(G), 1=Gyro(deg/s), 2=Magnetometer
  SensorTag(IMU) ~20Hz, 폰 ~200Hz.
반환 (N,6): [ax,ay,az(g), gx,gy,gz(rad/s)] — 50Hz 보간(20→50 업샘플, 충격디테일 한계).
용도: '학습=A셋 / 테스트=UMAFall' 로 device+population+rate 일반화 측정.
"""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np

POS = {"RIGHTPOCKET": 0, "CHEST": 1, "WAIST": 2, "WRIST": 3, "ANKLE": 4}
FS = 50.0
SRC_FS = 20.0          # SensorTag IMU
DEG2RAD = math.pi / 180.0


def _read_rows(csv: Path) -> np.ndarray:
    rows = []
    for l in open(csv, errors="ignore"):
        if not l or not l[0].isdigit():
            continue
        parts = l.strip().rstrip(";").split(";")
        if len(parts) < 7:
            continue
        try:
            rows.append([float(parts[i]) for i in range(7)])
        except ValueError:
            continue
    return np.asarray(rows) if rows else np.zeros((0, 7))


def _age(csv: Path) -> int:
    for l in open(csv, errors="ignore"):
        if l.startswith("% Age:"):
            m = re.findall(r"\d+", l)
            return int(m[0]) if m else -1
        if l and l[0].isdigit():
            break
    return -1


def load_trial(csv: Path, position: str = "WRIST") -> Tuple[np.ndarray, int, str, int]:
    csv = Path(csv)
    sid = POS[position]
    d = _read_rows(csv)
    label = 1 if "_Fall_" in csv.name else 0
    subj = re.search(r"Subject_\d+", csv.name)
    subj = subj.group(0) if subj else "NA"
    age = _age(csv)
    if len(d) == 0:
        return np.zeros((0, 6)), label, subj, age
    acc = d[(d[:, 6] == sid) & (d[:, 5] == 0)][:, 2:5]          # G
    gyr = d[(d[:, 6] == sid) & (d[:, 5] == 1)][:, 2:5] * DEG2RAD  # deg/s→rad/s
    if len(acc) < 4:
        return np.zeros((0, 6)), label, subj, age
    ta = np.arange(len(acc)) / SRC_FS
    grid = np.arange(0.0, ta[-1], 1.0 / FS)
    a = np.column_stack([np.interp(grid, ta, acc[:, c]) for c in range(3)])
    if len(gyr) >= 2:
        tg = np.arange(len(gyr)) / SRC_FS
        g = np.column_stack([np.interp(grid, tg, gyr[:, c]) for c in range(3)])
    else:
        g = np.zeros((len(grid), 3))
    return np.column_stack([a, g]), label, subj, age


def iter_dataset(root: Path, position: str = "WRIST",
                 min_age: Optional[int] = None) -> Iterator[Tuple[np.ndarray, int, str, int]]:
    for csv in sorted(Path(root).rglob("UMAFall_Subject_*.csv")):
        arr, lab, subj, age = load_trial(csv, position)
        if len(arr) == 0:
            continue
        if min_age is not None and age < min_age:
            continue
        yield arr, lab, subj, age
