"""PPG-DaLiA 로더 — 개인 HR×활동맥락(L1) 검증.

출처: UCI / Zenodo(10.5281/zenodo.3902728), CC BY 4.0.
구조: PPG_FieldStudy/S{1..15}/S{n}.pkl (pickle, latin1).
  data['signal']['wrist']['ACC']  : 32Hz 3축 가속도(Empatica E4, 단위 1/64 g)
  data['signal']['wrist']['BVP']  : 64Hz PPG
  data['label']                   : 기준 심박(bpm), 2초 윈도우/2초 시프트
  data['activity']                : 활동 ID (8종)
활용: 활동에서 맥락 추정 → '활동별 정상 HR' 모델(L1) 검증.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Dict, Iterator, Tuple

import numpy as np

ACC_FS = 32.0
ACTIVITY_NAMES = {
    0: "transient", 1: "sitting", 2: "stairs", 3: "table_soccer",
    4: "cycling", 5: "driving", 6: "lunch", 7: "walking", 8: "working",
}


def load_subject(pkl_path: Path) -> Dict:
    with open(pkl_path, "rb") as f:
        return pickle.load(f, encoding="latin1")


def subject_arrays(pkl_path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(wrist_acc_g (N,3), hr_bpm (M,), activity (M,)) 반환."""
    d = load_subject(pkl_path)
    # 이 pickle의 wrist ACC 는 이미 g 단위(범위 ±2g, 휴식 magnitude≈1) — 추가 스케일 금지.
    acc = np.asarray(d["signal"]["wrist"]["ACC"], float)
    hr = np.asarray(d["label"], float).ravel()           # 0.5Hz (2초 간격)
    act = np.asarray(d.get("activity", []), float).ravel()  # 4Hz
    return acc, hr, act


def iter_dataset(root: Path) -> Iterator[Tuple[str, np.ndarray, np.ndarray, np.ndarray]]:
    root = Path(root)
    for pkl in sorted(root.rglob("S*.pkl")):
        try:
            acc, hr, act = subject_arrays(pkl)
        except Exception:
            continue
        yield pkl.stem, acc, hr, act


def activity_to_context(activity_id: float) -> str:
    """PPG-DaLiA 활동 ID → WidU 활동맥락(REST/LOW/ACTIVE)."""
    a = int(activity_id)
    if a in (1, 5, 6):       # sitting/driving/lunch
        return "REST"
    if a in (8, 0):          # working/transient
        return "LOW"
    return "ACTIVE"          # walking/stairs/cycling/soccer
