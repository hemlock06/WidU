"""고령 낙상 recall 개선 — 진단 + 소프트폴 피처 A/B (실 SisFall).

가설: 고령 소프트폴(천천히 주저앉음)은 충격 피처상 ADL과 닮아 분류기가 놓침.
1) 진단: 고령 미탐이 '트리거(충격 부재)'냐 '분류(피처 부족)'냐 분해.
2) A/B: 기존 14피처 vs +소프트폴 피처. 고령 recall 개선폭 실측(피험자분할 OOF, 임계 0.4).
효과 있으면 widu.l2_fall.extract_features에 반영·재학습·재검증.
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.datasets import sisfall
from widu.preprocess import resample_antialiased, extract_window, smv
from widu.l2_fall import extract_features, FALL_FEATURES
from widu.augment import augment_train
from widu.eval.metrics import binary_metrics

TH = L2.FALL_PROBA_TH


def soft_features(w: np.ndarray) -> np.ndarray:
    """소프트폴(저충격) 식별용 추가 피처 — 충격 크기에 의존하지 않는 자세/정지 신호."""
    acc = w[:, 0:3].astype(float)
    s = smv(w)
    n = len(s)
    q = max(2, n // 4)
    a_first = acc[:q].mean(0)
    a_last = acc[-q:].mean(0)
    # 1) 자세 변화(초기 1/4 vs 말기 1/4) — 피크 무관, 느린 전이도 포착
    cos = float(np.dot(a_first, a_last) /
                (np.linalg.norm(a_first) * np.linalg.norm(a_last) + 1e-9))
    posture_change = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
    # 2) 말기 정지도(넘어진 뒤 가만)
    post_stillness = float(s[-q:].std())
    # 3) 저중력 비율(짧은 낙하 구간, 소프트폴에도 존재)
    low_g_frac = float((s < 0.8).mean())
    # 4) 낙하-안착 패턴(전반 최대 - 말기 평균)
    settle_drop = float(s[:max(n // 2, 1)].max() - s[-q:].mean())
    return np.array([posture_change, post_stillness, low_g_frac, settle_drop])


SOFT_NAMES = ["posture_change_deg", "post_stillness", "low_g_frac", "settle_drop"]


def load():
    root = ROOT / "data" / "SisFall"
    Wf, Xo, Xs, Y, SUBJ, ELD, TRIG = [], [], [], [], [], [], []
    t0 = time.time()
    for f in sorted(root.rglob("*.txt")):
        if f.name[0].upper() not in ("F", "D"):
            continue
        arr, lab = sisfall.load_file(f)
        if len(arr) == 0:
            continue
        a = resample_antialiased(arr, sisfall.FS, L2.FS)
        w = extract_window(a, L2.FS, L2.WIN_SEC, 0.75)
        if len(w) < int(L2.WIN_SEC * L2.FS * 0.5):
            continue
        Xo.append(extract_features(w, L2.FS))
        Xs.append(soft_features(w))
        TRIG.append(float(smv(w).max()) > L2.IMPACT_G)   # 충격 트리거 여부
        Y.append(lab); SUBJ.append(f.parent.name)
        ELD.append(f.parent.name.upper().startswith("SE"))
    print(f"로드 {len(Y)} {time.time()-t0:.0f}s")
    return (np.array(Xo), np.array(Xs), np.array(Y), np.array(SUBJ),
            np.array(ELD), np.array(TRIG))


def oof(X, Y, SUBJ, n_aug_feats=None):
    """특징행렬 X로 피험자분할 OOF 확률(증강은 윈도우 단계라 여기선 생략—피처 비교 목적)."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    p = np.full(len(Y), np.nan)
    for tr, te in GroupKFold(5).split(X, Y, SUBJ):
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1).fit(X[tr], Y[tr])
        p[te] = clf.predict_proba(X[te])[:, 1]
    return p


def recall_at(p, mask, th=TH):
    m = mask
    return float((p[m] >= th).mean()) if m.sum() else float("nan")


def main():
    Xo, Xs, Y, SUBJ, ELD, TRIG = load()
    fall = Y == 1
    eld_fall = ELD & fall
    adu_fall = (~ELD) & fall

    # --- 진단: 고령 미탐 = 트리거냐 분류냐 ---
    eld_trig_rate = float(TRIG[eld_fall].mean())
    adu_trig_rate = float(TRIG[adu_fall].mean())
    print("\n[진단] 충격 트리거율(>IMPACT_G):")
    print(f"  고령 낙상 {eld_trig_rate:.3f} / 성인 낙상 {adu_trig_rate:.3f}")
    print("  → 트리거율이 낮으면 '충격 부재(소프트폴)'가 원인, 높으면 '분류 피처' 문제")

    # --- A/B: 기존 vs +소프트폴 피처 ---
    p_old = oof(Xo, Y, SUBJ)
    Xn = np.hstack([Xo, Xs])
    p_new = oof(Xn, Y, SUBJ)

    res = {
        "diagnosis": {"elderly_trigger_rate": round(eld_trig_rate, 3),
                      "adult_trigger_rate": round(adu_trig_rate, 3)},
        "old_features": {
            "elderly_recall": round(recall_at(p_old, eld_fall), 3),
            "adult_recall": round(recall_at(p_old, adu_fall), 3),
            "f1": round(binary_metrics(Y, (p_old >= TH).astype(int)).f1, 3),
        },
        "with_softfall": {
            "elderly_recall": round(recall_at(p_new, eld_fall), 3),
            "adult_recall": round(recall_at(p_new, adu_fall), 3),
            "f1": round(binary_metrics(Y, (p_new >= TH).astype(int)).f1, 3),
        },
        "soft_features": SOFT_NAMES,
        "threshold": TH,
    }
    d_eld = res["with_softfall"]["elderly_recall"] - res["old_features"]["elderly_recall"]
    res["delta_elderly_recall"] = round(d_eld, 3)
    res["verdict"] = ("소프트폴 피처 채택 권장" if d_eld >= 0.02 else
                      "개선 미미 — within-window 한계 확인(L3 안전망이 본질)")
    (ROOT / "artifacts" / "softfall_ab.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[A/B] 임계", TH)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n판정: {res['verdict']} (Δ고령recall={d_eld:+.3f})")


if __name__ == "__main__":
    main()
