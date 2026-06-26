"""IMU 데이터 증강 — 낙상 학습용(원시 윈도우 Nx6 에 적용, 특징추출 전).

물리적으로 타당한 증강만 사용:
  - rotation : 임의 3D 회전(가속도·자이로에 '같은' 회전). 손목 착용 방향 불변성.
               회전은 벡터 크기 보존 → 중력 1g·각속도 크기 유지(물리 타당).
  - jitter   : 센서 노이즈(소).
  - scale    : 전체 진폭 미세 스케일(개체·기기 차).
  - time_warp: 부드러운 시간 왜곡(동작 속도 변이).
  - mag_warp : 부드러운 축별 진폭 왜곡.
금지: permutation/segment shuffle(낙상 시계열 구조 파괴), 축 무작위 뒤집기(비물리).

계약(중요): 증강은 **학습셋에만**, **분할 이후**에 적용한다(누수 방지).
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


def rotate(arr6: np.ndarray, rng: np.random.Generator,
           max_angle_deg: float = 60.0) -> np.ndarray:
    """가속도(0:3)·자이로(3:6)에 동일한 회전 적용(크기 보존).

    손목 착용 방향 분포는 제한적 → 전체 SO(3) 대신 회전각을 ±max_angle 로 bound.
    (full=180°는 손목에 비물리적인 자세를 생성해 일반화를 해칠 수 있음)
    """
    axis = rng.normal(size=3)
    axis /= (np.linalg.norm(axis) + 1e-12)
    angle = np.radians(rng.uniform(-max_angle_deg, max_angle_deg))
    R = Rotation.from_rotvec(axis * angle).as_matrix()
    out = arr6.copy()
    out[:, 0:3] = arr6[:, 0:3] @ R.T
    out[:, 3:6] = arr6[:, 3:6] @ R.T
    return out


def jitter(arr6: np.ndarray, rng: np.random.Generator,
           sigma_acc: float = 0.02, sigma_gyro: float = 0.05) -> np.ndarray:
    out = arr6.copy()
    out[:, 0:3] += rng.normal(0, sigma_acc, out[:, 0:3].shape)
    out[:, 3:6] += rng.normal(0, sigma_gyro, out[:, 3:6].shape)
    return out


def scale(arr6: np.ndarray, rng: np.random.Generator, lo: float = 0.9, hi: float = 1.1) -> np.ndarray:
    return arr6 * rng.uniform(lo, hi)


def _smooth_curve(n: int, knots: int, sigma: float, rng: np.random.Generator) -> np.ndarray:
    """제어점 보간으로 부드러운 1D 곡선(평균 1.0)."""
    xs = np.linspace(0, n - 1, knots)
    ys = rng.normal(1.0, sigma, knots)
    return np.interp(np.arange(n), xs, ys)


def mag_warp(arr6: np.ndarray, rng: np.random.Generator, sigma: float = 0.1, knots: int = 4) -> np.ndarray:
    n = len(arr6)
    out = arr6.copy()
    for c in range(6):
        out[:, c] = arr6[:, c] * _smooth_curve(n, knots, sigma, rng)
    return out


def time_warp(arr6: np.ndarray, rng: np.random.Generator, sigma: float = 0.1, knots: int = 4) -> np.ndarray:
    n = len(arr6)
    warp = np.cumsum(_smooth_curve(n, knots, sigma, rng))
    warp = warp / warp[-1] * (n - 1)               # 0..n-1 로 정규화(단조 증가)
    xp = np.arange(n)
    return np.column_stack([np.interp(warp, xp, arr6[:, c]) for c in range(6)])


_OPS = {
    "rotate": rotate, "jitter": jitter, "scale": scale,
    "mag_warp": mag_warp, "time_warp": time_warp,
}


# 기기별 회전각 bound — 손목은 자유롭게 돌아가고, 주머니 속 폰은 상대적으로 고정.
# 두 기기는 독립 위치이므로 회전은 '각각 독립'으로 적용해야 한다(같은 R 금지).
ROTATION_BOUND = {"watch": 70.0, "phone": 30.0}


def augment_window(arr6: np.ndarray, rng: np.random.Generator,
                   ops=("rotate", "jitter", "scale", "mag_warp"),
                   max_angle_deg: float = 60.0) -> np.ndarray:
    out = arr6
    for name in ops:
        if name == "rotate":
            out = rotate(out, rng, max_angle_deg)
        else:
            out = _OPS[name](out, rng)
    return out


def augment_dual(watch6: np.ndarray, phone6: np.ndarray, rng: np.random.Generator,
                 ops=("rotate", "jitter", "scale", "mag_warp")):
    """워치·폰 윈도우를 '각각 독립' 회전각으로 증강(같은 R 적용 금지).

    같은 회전을 두 기기에 적용하면 '강체로 결합'이라는 거짓 가정이 된다.
    """
    w = augment_window(watch6, rng, ops, max_angle_deg=ROTATION_BOUND["watch"])
    p = augment_window(phone6, rng, ops, max_angle_deg=ROTATION_BOUND["phone"])
    return w, p


def augment_train(windows, labels, groups, n_aug: int = 2, seed: int = 0,
                  ops=("rotate", "jitter", "scale", "mag_warp"),
                  balance: bool = True, max_angle_deg: float = 60.0):
    """학습셋 윈도우 증강. (분할 이후 호출 — 누수 방지 책임은 호출자)

    balance=True 면 소수 클래스(낙상)에 증강을 더 배정해 균형.
    반환: (windows_aug, labels_aug, groups_aug)  원본 포함.
    """
    rng = np.random.default_rng(seed)
    W = list(windows); Y = list(labels); G = list(groups)
    y = np.asarray(labels)
    n_pos = int((y == 1).sum()); n_neg = int((y == 0).sum())
    # 클래스별 증강 횟수
    aug_pos = n_aug
    aug_neg = n_aug
    if balance and n_pos > 0 and n_neg > 0 and n_pos != n_neg:
        # 적은 쪽을 더 증강
        if n_pos < n_neg:
            aug_pos = max(n_aug, int(round(n_aug * n_neg / n_pos)))
        else:
            aug_neg = max(n_aug, int(round(n_aug * n_pos / n_neg)))
    for w, lab, g in zip(windows, labels, groups):
        k = aug_pos if lab == 1 else aug_neg
        for _ in range(k):
            W.append(augment_window(np.asarray(w, float), rng, ops, max_angle_deg))
            Y.append(lab); G.append(g)
    return W, np.asarray(Y), np.asarray(G)
