"""낙상 평가·학습 스크립트 공유 헬퍼 — 중복 제거(DRY).

scripts/ 의 eval_*·train_*·optimize·strengthen·benchmark 가 동일하게 반복하던
(데이터셋→윈도우→특징, RF 팩토리, 표준 소스)을 한곳에 모은다. 모든 스크립트가
'동일 로직'을 쓰게 해 일관성·정확성도 높인다.

★주의: 서빙 경로(widu/pipeline·l2_fall)는 이 모듈을 import하지 않는다 — sklearn
의존을 분석 스크립트에만 격리(온디바이스/서빙 경량 유지).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, List, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from .config import L2
from .preprocess import resample_antialiased, extract_window
from .l2_fall import extract_features
from .datasets import sisfall, weda, umafall, smartfallmm as smm

DATA = Path(__file__).resolve().parents[1] / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)

# 표준 윈도우 = (window(N,6), label, subject)
Window = Tuple[np.ndarray, int, str]


def cache_windows(gen, src_fs: float, only_adl: bool = False) -> List[Window]:
    """데이터셋 제너레이터 → 추출 윈도우 목록. 학습/추론과 동일 전처리(안티앨리어싱·
    pre_frac=0.75 윈도우). only_adl=True 면 ADL(label 0)만."""
    out: List[Window] = []
    for arr, lab, subj, *_ in gen:
        if lab < 0 or len(arr) < 4 or (only_adl and lab != 0):
            continue
        a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
        w = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(w) >= MIN_WIN:
            out.append((np.asarray(w, float), int(lab), subj))
    return out


def feats(windows) -> np.ndarray:
    """윈도우 목록 → 특징 행렬(학습/추론 공유 extract_features)."""
    return np.array([extract_features(np.asarray(w, float), L2.FS) for w in windows])


def rf(n_estimators: int = 300, random_state: int = 0, **kw) -> RandomForestClassifier:
    """배포와 동일 규약의 RandomForest 팩토리(class_weight balanced·n_jobs -1)."""
    return RandomForestClassifier(n_estimators=n_estimators, class_weight="balanced",
                                  random_state=random_state, n_jobs=-1, **kw)


# --- 표준 데이터 소스(피험자 prefix 부여 — 데이터셋 간 충돌 방지) --- #
def src_weda(root: Path = None) -> Iterator[Window]:
    for arr, lab, subj, ft in weda.iter_dataset(root or DATA / "WEDA_raw"):
        yield arr, lab, f"WEDA_{subj}"


def src_uma(position: str, root: Path = None) -> Iterator[Window]:
    for arr, lab, subj, age in umafall.iter_dataset(root or DATA / "UMAFall_raw", position):
        yield arr, lab, f"UMA_{subj}"


def src_smm(group: str, position: str, root: Path = None) -> Iterator[Window]:
    for arr, lab, subj, act in smm.iter_dataset(root or DATA / "SmartFallMM", group, position):
        yield arr, lab, f"SMM_{subj}"


def src_sisfall(root: Path = None) -> Iterator[Window]:
    for arr, lab, meta in sisfall.iter_dataset(root or DATA / "SisFall"):
        yield arr, lab, f"SIS_{meta}"


# 소스별 네이티브 샘플레이트(cache_windows 의 src_fs 인자)
FS = {"weda": weda.FS, "uma": umafall.FS, "smm": smm.FS, "sisfall": sisfall.FS}
