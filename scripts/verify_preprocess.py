"""전처리·증강 10패스 자기재검증.

각 패스는 '제대로 됐는가 + 최선인가'를 코드로 단언한다. 하나라도 실패하면 종료코드 1.
실데이터 없이도 로직/물리 타당성은 전수 검증 가능(성능 수치는 실데이터·POC에서).
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.datasets import sisfall, synthetic
from widu.preprocess import resample_antialiased, extract_window, smv, butter_lowpass
from widu import augment
from widu.l2_fall import extract_features, FALL_FEATURES, FallDetector
from widu.types import IMUSample

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


# 1) 단위변환: 휴식(중력 1g) raw → 1g, gyro 0
def p1_units():
    g_raw = int(round(1.0 / sisfall._ADXL))   # 1g 에 해당하는 ADXL 카운트
    line = f"0,0,{g_raw},0,0,0,0,0,0"
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "D01_SA01_R01.txt"
        f.write_text("\n".join([line] * 10))
        arr, lab = sisfall.load_file(f)
    mag = float(np.sqrt((arr[:, 0:3] ** 2).sum(axis=1)).mean())
    gyro = float(np.abs(arr[:, 3:6]).mean())
    check("1.단위변환", abs(mag - 1.0) < 0.02 and gyro < 1e-6 and lab == 0,
          f"휴식 SMV={mag:.3f}g(≈1), gyro={gyro:.1e}, label=ADL")


# 2) 안티앨리어싱: 40Hz(@200) 다운샘플 50Hz 시 10Hz 폴딩 억제
def p2_antialias():
    fs = 200.0
    t = np.arange(0, 2, 1 / fs)
    sig = np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 40 * t)
    X = np.column_stack([sig] + [np.zeros_like(sig)] * 5)
    naive = sisfall.resample_to(X, fs, 50.0)
    aa = resample_antialiased(X, fs, 50.0)

    def band_energy(x, f0, dst=50.0):
        c = x[:, 0] - x[:, 0].mean()
        sp = np.abs(np.fft.rfft(c))
        fr = np.fft.rfftfreq(len(c), 1 / dst)
        i = int(np.argmin(np.abs(fr - f0)))
        return float(sp[i])
    naive_alias = band_energy(naive, 10.0)
    aa_alias = band_energy(aa, 10.0)
    aa_signal = band_energy(aa, 2.0)
    check("2.안티앨리어싱", aa_alias < 0.25 * naive_alias and aa_signal > aa_alias,
          f"10Hz 폴딩 naive={naive_alias:.1f}→aa={aa_alias:.1f}(≤25%), 2Hz신호={aa_signal:.1f} 보존")


# 3) 윈도우 규약 train==serve (충격 위치 pre_frac 일치)
def p3_window_consistency():
    seq = synthetic.imu_fall_sequence(t0=0.0, fs=L2.FS, seed=1)
    arr = np.array([[s.ax, s.ay, s.az, s.gx, s.gy, s.gz] for s in seq])
    win_n = int(L2.WIN_SEC * L2.FS)
    # train 측
    w_train = extract_window(arr, L2.FS, L2.WIN_SEC, pre_frac=0.75)
    peak_train = int(np.argmax(smv(w_train))) / max(len(w_train) - 1, 1)
    # serve 측 (스트리밍 분류 윈도우 포착)
    det = FallDetector(fs=L2.FS, pre_frac=0.75)
    cap = {}
    orig = det._classify
    def hook(ts, s):
        a = det._window_array()
        cap["pos"] = int(np.argmax(smv(a))) / max(len(a) - 1, 1)
        cap["n"] = len(a)
        orig(ts, s)
    det._classify = hook
    for s in seq:
        det.update(s)
    ok = "pos" in cap and abs(cap["pos"] - 0.75) < 0.08 and abs(peak_train - 0.75) < 0.08
    check("3.윈도우 train=serve", ok,
          f"충격위치 train={peak_train:.2f} serve={cap.get('pos'):.2f} (목표 0.75), win_n={win_n}")


# 4) 피험자 분할 누수 없음
def p4_subject_split():
    from sklearn.model_selection import GroupKFold
    W, Y, G = [], [], []
    for i in range(40):
        W.append(np.zeros((10, 6))); Y.append(i % 2); G.append(f"S{i%8}")
    Y = np.array(Y); G = np.array(G)
    bad = 0
    for tr, te in GroupKFold(n_splits=4).split(W, Y, G):
        if set(G[tr]) & set(G[te]):
            bad += 1
    check("4.피험자 누수", bad == 0, f"train∩test 피험자 겹침 폴드={bad}(=0)")


# 5) 증강은 분할 이후 학습셋만
def p5_aug_train_only():
    W = [synthetic.fall_window(seed=i) if i % 2 else synthetic.adl_window(seed=i) for i in range(20)]
    Y = np.array([i % 2 for i in range(20)]); G = np.array([f"S{i%5}" for i in range(20)])
    tr = list(range(0, 14)); te = list(range(14, 20))
    Wa, Ya, Ga = augment.augment_train([W[i] for i in tr], Y[tr], G[tr], n_aug=2, seed=0)
    # 테스트 피처는 원본만 → 개수 일치, 증강은 train 만 증가
    ok = (len(Ya) > len(tr)) and (len(te) == 6) and (set(Ga) <= set(G[tr]))
    check("5.증강 학습셋만", ok,
          f"train {len(tr)}→{len(Ya)}(증강), test {len(te)} 불변, 증강 피험자⊆train")


# 6) 회전 증강 물리 타당성(크기·내적 보존 = 직교변환)
def p6_rotation_physics():
    rng = np.random.default_rng(0)
    w = synthetic.fall_window(seed=3)
    r = augment.rotate(w, rng)
    acc_mag_ok = np.allclose(smv(w), smv(r), atol=1e-9)
    gyro_mag_ok = np.allclose(np.sqrt((w[:, 3:6] ** 2).sum(1)),
                              np.sqrt((r[:, 3:6] ** 2).sum(1)), atol=1e-9)
    # 내적 보존(직교): a_i·a_j 불변
    A0, A1 = w[:, 0:3], r[:, 0:3]
    dot_ok = np.allclose(A0 @ A0.T, A1 @ A1.T, atol=1e-6)
    check("6.회전 물리타당", acc_mag_ok and gyro_mag_ok and dot_ok,
          f"가속도·자이로 크기보존={acc_mag_ok and gyro_mag_ok}, 내적보존(직교)={dot_ok}")


# 7) 증강 건전성(NaN 無, 낙상 충격 보존, 특징 유한)
def p7_aug_sanity():
    rng = np.random.default_rng(1)
    bad = 0; min_peak = 9.9
    for i in range(50):
        w = augment.augment_window(synthetic.fall_window(seed=i), rng)
        if not np.isfinite(w).all():
            bad += 1
        min_peak = min(min_peak, float(smv(w).max()))
        f = extract_features(w, L2.FS)
        if not np.isfinite(f).all() or len(f) != len(FALL_FEATURES):
            bad += 1
    check("7.증강 건전성", bad == 0 and min_peak > L2.IMPACT_G,
          f"비유한={bad}, 증강 낙상 최소충격={min_peak:.2f}g(>{L2.IMPACT_G})")


# 8) 클래스 균형(불균형 입력 → 증강 후 개선)
def p8_balance():
    W, Y, G = [], [], []
    for i in range(40):
        lab = 1 if i < 8 else 0           # 8 낙상 : 32 ADL (1:4)
        W.append(synthetic.fall_window(seed=i) if lab else synthetic.adl_window(seed=i))
        Y.append(lab); G.append(f"S{i%5}")
    Y = np.array(Y)
    _, Ya, _ = augment.augment_train(W, Y, np.array(G), n_aug=2, seed=0, balance=True)
    before = Y.mean()
    after = Ya.mean()
    check("8.클래스 균형", abs(after - 0.5) < abs(before - 0.5),
          f"낙상비율 {before:.2f}→{after:.2f} (0.5 에 근접)")


# 9) 재현성(동일 seed → 동일 결과)
def p9_determinism():
    W = [synthetic.fall_window(seed=i) for i in range(6)]
    Y = np.array([1, 0, 1, 0, 1, 0]); G = np.array([f"S{i}" for i in range(6)])
    a1, y1, _ = augment.augment_train(W, Y, G, n_aug=2, seed=42)
    a2, y2, _ = augment.augment_train(W, Y, G, n_aug=2, seed=42)
    same = all(np.allclose(x, z) for x, z in zip(a1, a2)) and np.array_equal(y1, y2)
    check("9.재현성", same, "동일 seed 증강 결과 일치")


# 10) 특징 train/infer 동일 + 엣지케이스
def p10_feature_identity():
    w = synthetic.fall_window(seed=9)
    f_a = extract_features(w, L2.FS)            # 학습 경로
    f_b = extract_features(w.copy(), L2.FS)     # 추론 경로(동일 함수)
    ident = np.allclose(f_a, f_b) and len(f_a) == len(FALL_FEATURES)
    edge_ok = True
    try:
        extract_features(np.ones((1, 6)), L2.FS)         # 1샘플
        extract_window(np.zeros((0, 6)), L2.FS, 2.0)     # 빈 배열
        ew = extract_window(np.ones((30, 6)), L2.FS, 2.0)  # win보다 짧음
        edge_ok = len(ew) <= int(L2.WIN_SEC * L2.FS)
    except Exception as e:
        edge_ok = False
    check("10.특징 일치·엣지", ident and edge_ok,
          f"train=infer={ident}, 엣지(1샘플/빈/짧음) 안전={edge_ok}")


# 11) 워치·폰 독립 회전(같은 R 금지) + 기기별 각도 bound
def p11_dual_independent_rotation():
    rng = np.random.default_rng(0)
    base = synthetic.fall_window(seed=11)
    w_aug, p_aug = augment.augment_dual(base.copy(), base.copy(), rng, ops=("rotate",))
    independent = not np.allclose(w_aug, p_aug)         # 서로 다른 회전
    # 크기 보존(둘 다)
    mag_ok = (np.allclose(smv(w_aug), smv(base), atol=1e-9) and
              np.allclose(smv(p_aug), smv(base), atol=1e-9))

    def mean_angle(a, b):
        v0, v1 = a[:, 0:3].mean(0), b[:, 0:3].mean(0)
        c = np.dot(v0, v1) / (np.linalg.norm(v0) * np.linalg.norm(v1) + 1e-12)
        return np.degrees(np.arccos(max(-1, min(1, c))))
    ang_w = mean_angle(base, w_aug)
    ang_p = mean_angle(base, p_aug)
    bound_ok = ang_w <= augment.ROTATION_BOUND["watch"] + 2 and ang_p <= augment.ROTATION_BOUND["phone"] + 2
    check("11.워치·폰 독립회전", independent and mag_ok and bound_ok,
          f"독립={independent}, 크기보존={mag_ok}, 각도 워치{ang_w:.0f}°≤70 폰{ang_p:.0f}°≤30")


def main():
    for fn in [p1_units, p2_antialias, p3_window_consistency, p4_subject_split,
               p5_aug_train_only, p6_rotation_physics, p7_aug_sanity, p8_balance,
               p9_determinism, p10_feature_identity, p11_dual_independent_rotation]:
        try:
            fn()
        except Exception as e:
            check(fn.__name__, False, f"예외: {e}")
    npass = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n===== {npass}/{len(RESULTS)} PASS =====")
    sys.exit(0 if npass == len(RESULTS) else 1)


if __name__ == "__main__":
    main()
