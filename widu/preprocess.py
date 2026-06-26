"""신호 전처리 — 리샘플(안티앨리어싱)·윈도우·정규화.

설계 결함 교정:
  (1) 다운샘플 전 저역통과(Butterworth) → 에일리어싱 방지.
  (2) 윈도우 규약을 '서빙(스트리밍)'과 일치: 충격이 윈도우 내 pre_frac 위치에
      오도록(기본 0.75 = 충격 후 0.25*win 만큼의 사후 맥락 포함). 학습=추론 동일.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from scipy import signal


def butter_lowpass(arr: np.ndarray, cutoff_hz: float, fs: float, order: int = 4) -> np.ndarray:
    """열별 영위상 저역통과 필터(filtfilt)."""
    if len(arr) <= 3 * order:
        return arr
    nyq = 0.5 * fs
    wn = min(0.99, cutoff_hz / nyq)
    b, a = signal.butter(order, wn, btype="low")
    return np.column_stack([signal.filtfilt(b, a, arr[:, c]) for c in range(arr.shape[1])])


def resample_antialiased(arr: np.ndarray, src_fs: float, dst_fs: float) -> np.ndarray:
    """안티앨리어싱 후 선형 리샘플.

    다운샘플 시 컷오프 = 0.8 * (dst_fs/2) 로 저역통과 → 폴딩 방지.
    업샘플은 필터 불필요.
    """
    if len(arr) == 0 or abs(src_fs - dst_fs) < 1e-6:
        return arr
    work = arr
    if dst_fs < src_fs:
        work = butter_lowpass(arr, cutoff_hz=0.8 * (dst_fs / 2.0), fs=src_fs)
    n_dst = max(1, int(round(len(work) * dst_fs / src_fs)))
    xs = np.linspace(0, len(work) - 1, n_dst)
    xp = np.arange(len(work))
    return np.column_stack([np.interp(xs, xp, work[:, c]) for c in range(work.shape[1])])


def smv(acc: np.ndarray) -> np.ndarray:
    return np.sqrt((acc[:, 0:3] ** 2).sum(axis=1))


def extract_window(arr: np.ndarray, fs: float, win_sec: float = 2.0,
                   pre_frac: float = 0.75, peak_idx: Optional[int] = None) -> np.ndarray:
    """충격(peak) 기준 윈도우. 충격이 윈도우 내 pre_frac 위치에 오도록.

    서빙(스트리밍)에서도 동일 규약을 쓴다(충격 트리거 후 (1-pre_frac)*win 만큼
    사후 샘플을 더 모은 뒤 같은 윈도우를 잘라 분류). → train/serve 일치.
    """
    n = len(arr)
    win_n = int(round(win_sec * fs))
    if n == 0:
        return arr
    if peak_idx is None:
        peak_idx = int(np.argmax(smv(arr)))
    pre = int(round(win_n * pre_frac))
    start = peak_idx - pre
    end = start + win_n
    # 경계 보정(가장자리 패딩 대신 클램프 후 길이 보장)
    if start < 0:
        start, end = 0, min(n, win_n)
    if end > n:
        end, start = n, max(0, n - win_n)
    return arr[start:end]


def zscore_fit(X: np.ndarray):
    """특징 표준화 파라미터(평균/표준편차) — 학습셋에서만 fit."""
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-8] = 1.0
    return mu, sd


def zscore_apply(X: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return (X - mu) / sd
