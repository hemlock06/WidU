"""고령 ADL 오탐(24%) 처방 검증 — '고령 ADL을 학습에 넣으면 줄어드나?'

사용자 질문의 핵심: 표적 데이터(고령 ADL)가 실제로 갭을 닫나?
정직한 설계: 고령 피험자를 분할(GroupKFold). 학습=젊은층 전부 + 고령ADL '학습 피험자',
테스트=완전히 빼둔 '테스트 피험자'의 고령 ADL 오탐율. (피험자 누수 없음)
 - 베이스라인: 젊은층만 학습 → 테스트 고령 오탐율
 - 처방: 젊은층 + 학습측 고령ADL → 테스트 고령 오탐율
처방이 낮추면=표적 고령데이터가 답. 안 낮추면=고령 '낙상'까지 필요(데이터로 못 사는 갭).
산출 → artifacts/elderly_mitigation_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.preprocess import extract_window
from widu.l2_fall import extract_features
from widu.datasets import weda, umafall, smartfallmm as smm

DATA = ROOT / "data"
MIN_WIN = int(L2.WIN_SEC * L2.FS * 0.5)


def windows(gen, src_fs=L2.FS):
    from widu.preprocess import resample_antialiased
    X, y, g = [], [], []
    for arr, lab, subj, *_ in gen:
        if lab < 0 or len(arr) < 4:
            continue
        a = arr if src_fs == L2.FS else resample_antialiased(arr, src_fs, L2.FS)
        win = extract_window(a, L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) < MIN_WIN:
            continue
        X.append(extract_features(np.asarray(win, float), L2.FS)); y.append(int(lab)); g.append(subj)
    return np.array(X), np.array(y), np.array(g)


def _rf():
    return RandomForestClassifier(n_estimators=300, class_weight="balanced",
                                  random_state=0, n_jobs=-1)


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    th = L2.FALL_PROBA_TH
    # 젊은층 손목 전부(WEDA+UMAFall-wrist+SMM young watch) = 공통 학습 기반
    Xy, yy, _ = windows(((a, l, s) for a, l, s, _ in weda.iter_dataset(DATA / "WEDA_raw")))
    Xu, yu, _ = windows(((a, l, s) for a, l, s, _ in umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST")))
    Xs, ys, _ = windows(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"))
    Xyoung = np.vstack([Xy, Xu, Xs]); yyoung = np.concatenate([yy, yu, ys])
    print(f"젊은층 손목 학습기반: {len(yyoung)} windows (낙상 {int(yyoung.sum())})", flush=True)

    # 고령 ADL(손목) — 피험자 그룹
    Xo, yo, go = windows(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"))
    Xo = Xo[yo == 0]; go = go[yo == 0]      # 고령은 ADL뿐
    print(f"고령 ADL 손목: {len(Xo)} windows, 피험자 {len(set(go))}", flush=True)

    gkf = GroupKFold(n_splits=5)
    base_fp, mit_fp = [], []
    for tr, te in gkf.split(Xo, np.zeros(len(Xo)), go):
        Xo_tr, Xo_te = Xo[tr], Xo[te]
        # 베이스라인: 젊은층만
        clf0 = _rf().fit(Xyoung, yyoung)
        base_fp.append(float((clf0.predict_proba(Xo_te)[:, 1] >= th).mean()))
        # 처방: 젊은층 + 학습측 고령ADL(음성으로)
        Xmit = np.vstack([Xyoung, Xo_tr]); ymit = np.concatenate([yyoung, np.zeros(len(Xo_tr), int)])
        clf1 = _rf().fit(Xmit, ymit)
        mit_fp.append(float((clf1.predict_proba(Xo_te)[:, 1] >= th).mean()))

    report = {
        "threshold": th,
        "baseline_young_only": {
            "elderly_adl_fp_mean": round(float(np.mean(base_fp)), 3),
            "per_fold": [round(x, 3) for x in base_fp],
        },
        "mitigation_add_elderly_adl": {
            "elderly_adl_fp_mean": round(float(np.mean(mit_fp)), 3),
            "per_fold": [round(x, 3) for x in mit_fp],
        },
        "reduction_abs": round(float(np.mean(base_fp) - np.mean(mit_fp)), 3),
        "interpretation": "처방 FP가 베이스라인보다 크게 낮으면 표적 고령ADL이 오탐 갭의 답. "
                          "단 고령 '낙상' recall은 여전히 미해결(고령 낙상 데이터 부재).",
    }
    print("\n=== 고령 ADL 오탐 처방 검증(피험자 분할) ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    (ROOT / "artifacts" / "elderly_mitigation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
