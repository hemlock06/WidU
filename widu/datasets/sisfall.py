"""SisFall 로더 — 낙상(L2) 학습/검증 핵심 데이터셋.

출처: http://sistemic.udea.edu.co/en/research/projects/english-falls/
파일명 규약: F##_SA##_R##.txt (낙상) / D##_SA##_R##.txt (일상활동, ADL)
각 줄(쉼표구분 9값): ADXL345(ax,ay,az), ITG3200(gx,gy,gz), MMA8451Q(ax,ay,az)
샘플레이트 200Hz.
변환:
  ADXL345  ±16g, 13bit  → g    = raw * (2*16)/(2^13)
  ITG3200  ±2000°/s 16bit → °/s = raw * (2*2000)/(2^16)  → rad/s
반환 (N,6): [ax,ay,az(g), gx,gy,gz(rad/s)]  ← WidU 표준 IMU 계약
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterator, List, Tuple

import numpy as np

FS = 200.0
_ADXL = (2 * 16.0) / (2 ** 13)
_ITG_DEG = (2 * 2000.0) / (2 ** 16)
_DEG2RAD = math.pi / 180.0


def load_file(path: Path) -> Tuple[np.ndarray, int]:
    """SisFall 파일 → (arr (N,6), label) label: 1=낙상 0=ADL."""
    path = Path(path)
    rows = []
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip().rstrip(";").strip()
        if not line:
            continue
        parts = [p for p in line.replace(";", "").split(",") if p.strip() != ""]
        if len(parts) < 9:
            continue
        try:
            v = [float(x) for x in parts[:9]]
        except ValueError:
            continue
        rows.append(v)
    raw = np.asarray(rows, dtype=float)
    if raw.size == 0:
        return np.zeros((0, 6)), _label(path)
    acc = raw[:, 0:3] * _ADXL                       # g
    gyro = raw[:, 3:6] * _ITG_DEG * _DEG2RAD        # rad/s
    arr = np.column_stack([acc, gyro])
    return arr, _label(path)


def _label(path: Path) -> int:
    return 1 if path.name.upper().startswith("F") else 0


def iter_dataset(root: Path) -> Iterator[Tuple[np.ndarray, int, str]]:
    """root 아래 모든 *.txt → (arr, label, subject)."""
    root = Path(root)
    for f in sorted(root.rglob("*.txt")):
        if f.name[0].upper() not in ("F", "D"):
            continue
        arr, lab = load_file(f)
        if len(arr) == 0:
            continue
        subj = f.name.split("_")[1] if "_" in f.name else "NA"
        yield arr, lab, subj


def peak_window(arr: np.ndarray, win_sec: float = 2.0, fs: float = FS) -> np.ndarray:
    """충격 피크 중심 윈도우 추출(특징 추출용)."""
    smv = np.sqrt((arr[:, 0:3] ** 2).sum(axis=1))
    if len(smv) == 0:
        return arr
    peak = int(np.argmax(smv))
    half = int(win_sec * fs / 2)
    s = max(0, peak - half)
    e = min(len(arr), peak + half)
    return arr[s:e]


def resample_to(arr: np.ndarray, src_fs: float, dst_fs: float) -> np.ndarray:
    """간단 선형 리샘플 (200Hz → 50Hz 등)."""
    if abs(src_fs - dst_fs) < 1e-6 or len(arr) == 0:
        return arr
    n_dst = max(1, int(len(arr) * dst_fs / src_fs))
    xs = np.linspace(0, len(arr) - 1, n_dst)
    xp = np.arange(len(arr))
    return np.column_stack([np.interp(xs, xp, arr[:, c]) for c in range(arr.shape[1])])
