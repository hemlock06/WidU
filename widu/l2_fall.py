"""L2 — 낙상 탐지 (가속도+자이로).

최우선 신규 AI. accel+gyro 가 이미 100Hz 로 들어오고(WIDYU SCRUM 데이터계약),
공개 라벨 데이터(SisFall 등)가 존재하는 유일한 항목.

설계:
  - 배터리: 2단계. 저비용 충격 트리거(|SMV|>IMPACT_G) → 그때만 윈도우 분류.
  - 특징: 자유낙하→충격→자세변화→사후 무활동의 물리 시그니처.
  - 모델: RandomForest(SisFall/FallAllD 학습). 모델 없으면 임계 휴리스틱으로 동작.
  - 확정: 충격 + 사후 무활동(일어나지 못함) → 위급 격상(ADL 오탐 억제).
특징 추출기는 학습 스크립트(scripts/train_fall.py)와 공유한다.
"""
from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import List, Optional

import numpy as np
from scipy.stats import kurtosis, skew

from .types import IMUSample, AlertLevel, Detection
from .config import L2

# 학습/추론이 반드시 같은 순서를 쓰도록 명시.
# base(0~13) + extra(14~22): extra는 스펙트럼·첨도·피크 등 낙상 vs 손동작 변별
# (손목 LODO F1 0.713→0.744, 허리 무해 0.949→0.951; strengthen_wrist_features 검증).
# ★휴리스틱 폴백(fall_proba)이 feat[0,1,2,12,13]을 쓰므로 extra는 반드시 '끝'에 추가.
FALL_FEATURES: List[str] = [
    "acc_max", "acc_min", "acc_range", "acc_mean", "acc_std",
    "jerk_max", "sma",
    "gyro_max", "gyro_mean", "gyro_std",
    "pre_std", "post_std", "orient_change_deg", "freefall_depth",
    # extra
    "smv_kurtosis", "smv_skew", "dom_freq", "band_1_3hz", "band_3_8hz",
    "peak_count", "settle_ratio", "autocorr_peak", "gyro_acc_corr",
]


def _smv(acc: np.ndarray) -> np.ndarray:
    """행 단위 가속도 크기(g). acc: (N,3)."""
    return np.sqrt((acc ** 2).sum(axis=1))


def extract_features(win: np.ndarray, fs: float = L2.FS) -> np.ndarray:
    """윈도우(N,6: ax,ay,az,gx,gy,gz, 가속도는 g 단위)에서 특징 벡터.

    학습과 추론이 동일 함수를 사용한다.
    """
    acc = win[:, 0:3].astype(float)
    gyro = win[:, 3:6].astype(float)
    smv = _smv(acc)
    n = len(smv)
    peak_i = int(np.argmax(smv))

    acc_max = float(smv.max())
    acc_min = float(smv.min())
    acc_range = acc_max - acc_min
    acc_mean = float(smv.mean())
    acc_std = float(smv.std())

    jerk = np.abs(np.diff(smv)) * fs
    jerk_max = float(jerk.max()) if len(jerk) else 0.0
    sma = float(np.abs(acc - acc.mean(axis=0)).sum() / max(n, 1))

    gmag = np.sqrt((gyro ** 2).sum(axis=1))
    gyro_max = float(gmag.max())
    gyro_mean = float(gmag.mean())
    gyro_std = float(gmag.std())

    pre = smv[:peak_i] if peak_i > 1 else smv[:1]
    post = smv[peak_i:] if peak_i < n - 1 else smv[-1:]
    pre_std = float(pre.std())
    post_std = float(post.std())

    # 자세 변화: 충격 전/후 평균 가속도 벡터 사이 각도
    a_pre = acc[:max(peak_i, 1)].mean(axis=0)
    a_post = acc[peak_i:].mean(axis=0)
    cos = float(np.dot(a_pre, a_post) /
                (np.linalg.norm(a_pre) * np.linalg.norm(a_post) + 1e-9))
    orient_change_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos))))

    # 자유낙하 깊이: 충격 전 최저 SMV 가 얼마나 0g 에 가까웠나
    freefall_depth = float(max(0.0, 1.0 - (pre.min() if len(pre) else 1.0)))

    base = np.array([
        acc_max, acc_min, acc_range, acc_mean, acc_std,
        jerk_max, sma, gyro_max, gyro_mean, gyro_std,
        pre_std, post_std, orient_change_deg, freefall_depth,
    ], dtype=float)
    return np.concatenate([base, _extra_feats(acc, gyro, smv, peak_i, fs)])


def _extra_feats(acc: np.ndarray, gyro: np.ndarray, smv: np.ndarray,
                 peak_i: int, fs: float) -> np.ndarray:
    """추가 변별 특징(스펙트럼·첨도·피크·정착·주기성). 충격 이벤트 시에만 호출되므로
    FFT 비용 허용. 모두 학습/추론 공유(extract_features 내부)."""
    n = len(smv)
    s0 = smv - smv.mean()
    kurt = float(kurtosis(smv)) if n > 3 else 0.0
    sk = float(skew(smv)) if n > 2 else 0.0
    fftmag = np.abs(np.fft.rfft(s0))
    freqs = np.fft.rfftfreq(n, 1.0 / fs)
    tot = float(fftmag.sum()) + 1e-9
    dom = float(freqs[np.argmax(fftmag)]) if len(fftmag) > 1 else 0.0
    band_lo = float(fftmag[(freqs >= 1) & (freqs < 3)].sum() / tot)
    band_hi = float(fftmag[(freqs >= 3) & (freqs < 8)].sum() / tot)
    thr = smv.mean() + smv.std()
    peaks = int(((smv[1:-1] > smv[:-2]) & (smv[1:-1] > smv[2:]) & (smv[1:-1] > thr)).sum()) if n > 2 else 0
    pre_e = float((s0[:max(peak_i, 1)] ** 2).mean())
    post_e = float((s0[peak_i:] ** 2).mean()) if peak_i < n - 1 else 0.0
    settle = post_e / (pre_e + 1e-9)
    ac = np.correlate(s0, s0, "full")[n - 1:]
    ac = ac / (ac[0] + 1e-9)
    acpk = float(ac[1:].max()) if n > 2 else 0.0
    gmag = np.sqrt((gyro ** 2).sum(axis=1))
    cc = float(np.corrcoef(smv, gmag)[0, 1]) if n > 2 and gmag.std() > 0 else 0.0
    return np.array([kurt, sk, dom, band_lo, band_hi, peaks, settle, acpk, cc], float)


class FallModel:
    """RandomForest 래퍼. 모델 파일 없으면 임계 휴리스틱으로 폴백."""

    def __init__(self, path: Path = L2.MODEL_PATH):
        self.model = None
        self.path = Path(path)
        if self.path.exists():
            try:
                import joblib
                self.model = joblib.load(self.path)
            except Exception:
                self.model = None

    @property
    def trained(self) -> bool:
        return self.model is not None

    def fall_proba(self, feat: np.ndarray) -> float:
        if self.model is not None:
            return float(self.model.predict_proba(feat.reshape(1, -1))[0, 1])
        # 휴리스틱: 충격 크고 + 자유낙하 + 자세변화 큼
        acc_max, _, acc_range = feat[0], feat[1], feat[2]
        orient, freefall = feat[12], feat[13]
        score = 0.0
        score += 0.4 if acc_max > L2.IMPACT_G else 0.0
        score += 0.2 if acc_range > 1.5 else 0.0
        score += 0.2 if orient > 45 else 0.0
        score += 0.2 if freefall > 0.4 else 0.0
        return score


class FallDetector:
    """스트리밍 낙상 탐지(사용자 1인).

    윈도우 규약을 학습과 일치시킨다:
      충격 트리거 → 사후 (1-pre_frac)*win 샘플을 더 모은 뒤 → 분류.
    그래야 분류 윈도우에서 충격이 pre_frac 위치에 오고, 학습(extract_window)과 동일.
    """

    def __init__(self, fs: float = L2.FS, model: Optional[FallModel] = None,
                 pre_frac: float = 0.75, source: str = "watch"):
        self.source = source
        # 위치별 임계(손목 0.30·허리 0.40). source 없으면 기본값.
        self.proba_th = L2.FALL_PROBA_TH_BY_SOURCE.get(source, L2.FALL_PROBA_TH)
        self.fs = fs
        self.win_n = int(L2.WIN_SEC * fs)
        self.pre_frac = pre_frac
        self.post_n = max(1, self.win_n - int(round(self.win_n * pre_frac)))
        self.buf: deque[IMUSample] = deque(maxlen=self.win_n)
        self.model = model or FallModel()
        self._collect = 0                 # 남은 사후수집 샘플 수
        self._post_smv: deque[float] = deque(maxlen=int(L2.POST_IMMOBILE_SEC * fs))
        self._candidate_ts: Optional[float] = None
        self._candidate_proba: float = 0.0
        self._candidate_hard: bool = False   # 후보가 '센 충격(분류기 무관)'으로 떴나
        self._candidate_impact: float = 0.0
        self.impact_fired: bool = False   # 이번 update 에서 충격 트리거 발생?
        self.last_impact_g: float = 0.0

    def _window_array(self) -> np.ndarray:
        return np.array([[s.ax, s.ay, s.az, s.gx, s.gy, s.gz] for s in self.buf], float)

    def _classify(self, ts: float, smv: float) -> Optional[Detection]:
        feat = extract_features(self._window_array(), self.fs)
        proba = self.model.fall_proba(feat)
        hard = self.last_impact_g >= L2.IMPACT_HARD_G   # 분류기 무관 안전망
        if proba >= self.proba_th or hard:
            self._candidate_ts = ts
            self._candidate_proba = proba
            self._candidate_hard = bool(hard and proba < self.proba_th)
            self._candidate_impact = self.last_impact_g
            self._post_smv.clear()
            self._post_smv.append(smv)
            return None
        # 회색지대(충격은 있고 확신 부족) → 의심 → 능동 확인 루프 유도(파이프라인이 self-check 무장)
        if proba >= L2.FALL_PROBA_SOFT:
            return Detection("L2", AlertLevel.CAUTION, "fall_suspected", proba, ts,
                             {"fall_proba": round(proba, 2),
                              "impact_g": round(self.last_impact_g, 1),
                              "source": self.source}, source=self.source)
        return None

    def update(self, s: IMUSample) -> Optional[Detection]:
        self.impact_fired = False
        self.buf.append(s)
        smv = math.sqrt(s.ax ** 2 + s.ay ** 2 + s.az ** 2)
        if smv > L2.IMPACT_G and len(self.buf) >= self.win_n:
            self.impact_fired = True
            self.last_impact_g = smv

        # (A) 낙상 후보 → 사후 무활동(long-lie) 관찰
        if self._candidate_ts is not None:
            self._post_smv.append(smv)
            if s.ts - self._candidate_ts >= L2.POST_IMMOBILE_SEC:
                immobile = float(np.array(self._post_smv).std()) < L2.POST_IMMOBILE_STD
                ts0, proba = self._candidate_ts, self._candidate_proba
                hard, impact = self._candidate_hard, self._candidate_impact
                self._candidate_ts = None
                self._candidate_hard = False
                self._post_smv.clear()
                # 무활동 동반 → 위급. 분류기(proba≥th) OR 센 충격(분류기 무관 안전망).
                # 센 충격 단독(분류기 미탐)은 confidence를 충격강도로 부여.
                if immobile and (proba >= self.proba_th or hard):
                    conf = min(1.0, proba + 0.2) if proba >= self.proba_th \
                        else min(0.9, 0.55 + (impact - L2.IMPACT_HARD_G) * 0.1)
                    return Detection("L2", AlertLevel.EMERGENCY, "fall_long_lie",
                                     conf, ts0,
                                     {"fall_proba": round(proba, 2),
                                      "impact_g": round(impact, 1),
                                      "impact_driven": bool(hard),
                                      "post_immobile_s": L2.POST_IMMOBILE_SEC,
                                      "source": self.source}, source=self.source)
                # 무활동 없이 회복 → CAUTION은 분류기 동의 시에만(센 충격 단독은 단순 부딪힘=무발화)
                if proba >= self.proba_th:
                    return Detection("L2", AlertLevel.CAUTION, "fall_recovered",
                                     proba, ts0, {"fall_proba": round(proba, 2),
                                                  "source": self.source}, source=self.source)
            return None

        # (B) 충격 후 사후맥락 수집 단계 → 다 모이면 분류(학습 규약과 일치)
        if self._collect > 0:
            self._collect -= 1
            if self._collect == 0 and len(self.buf) >= self.win_n:
                return self._classify(s.ts, smv)   # 회색지대면 fall_suspected 반환
            return None

        # (C) 충격 트리거 → 사후수집 시작
        if smv > L2.IMPACT_G and len(self.buf) >= self.win_n:
            self._collect = self.post_n
        return None
