"""최종 배포 낙상모델 재학습 — 최적화에서 고른 승리 구성으로 전체 데이터 학습.

배포 모델은 holdout 없이 가용 전 데이터로 학습(일반화 추정치는 LODO가 이미 제공).
승리 구성(기본): 모든 젊은 소스(낙상+ADL) + 고령 ADL(음성) + 증강(위치별 회전각).
기존 models/*.joblib 은 .bak 백업 후 덮어씀. 학습 후 피험자분할 CV sanity 출력.

사용: python scripts/train_fall_final.py --position wrist --smm --elderly --aug
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sklearn.model_selection import GroupKFold

from widu.config import L2
from widu.l2_fall import FallModel
from widu.augment import augment_train, ROTATION_BOUND
from widu.eval.metrics import binary_metrics
from widu.datasets import sisfall, weda, umafall, smartfallmm as smm
from widu.falleval import cache_windows as cache, feats, rf, DATA   # 공유 헬퍼(DRY)


def gather(position, use_smm, use_elderly):
    wins, ys, gs = [], [], []
    def add(items, tag):
        for w, l, s in items:
            wins.append(w); ys.append(l); gs.append(f"{tag}_{s}")
    if position == "wrist":
        add(cache(weda.iter_dataset(DATA / "WEDA_raw"), weda.FS), "WEDA")
        add(cache(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS), "UMA")
        if use_smm:
            add(cache(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS), "SMM")
        if use_elderly:
            add(cache(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS, only_adl=True), "OLD")
        angle = ROTATION_BOUND["watch"]; out = L2.MODEL_PATH_WRIST
    else:
        add(cache(sisfall.iter_dataset(DATA / "SisFall"), sisfall.FS), "SIS")
        add(cache(umafall.iter_dataset(DATA / "UMAFall_raw", "WAIST"), umafall.FS), "UMA")
        if use_smm:
            add(cache(smm.iter_dataset(DATA / "SmartFallMM", "young", "phone"), smm.FS), "SMM")
        if use_elderly:
            add(cache(smm.iter_dataset(DATA / "SmartFallMM", "old", "phone"), smm.FS, only_adl=True), "OLD")
        angle = ROTATION_BOUND["phone"]; out = L2.MODEL_PATH_WAIST
    return wins, np.array(ys), np.array(gs), angle, out




def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--position", choices=["wrist", "waist"], required=True)
    ap.add_argument("--smm", action="store_true")
    ap.add_argument("--elderly", action="store_true")
    ap.add_argument("--aug", action="store_true")
    a = ap.parse_args()

    wins, y, g, angle, out_path = gather(a.position, a.smm, a.elderly)
    print(f"[{a.position}] {len(y)} windows (낙상 {int(y.sum())}/ADL {int((y==0).sum())}) "
          f"피험자 {len(set(g))} | smm={a.smm} elderly={a.elderly} aug={a.aug}")

    # 피험자분할 CV sanity(누수없음) — 배포 전 recall 가드
    gkf = GroupKFold(n_splits=5)
    sens, prec, f1 = [], [], []
    for tr, te in gkf.split(wins, y, g):
        trw = [wins[i] for i in tr]; trY = y[tr]; trG = g[tr]
        if a.aug:
            W, Y, _ = augment_train(trw, list(trY), list(trG), n_aug=2, seed=0, max_angle_deg=angle)
            Xtr = feats(W); ytr = Y
        else:
            Xtr = feats(trw); ytr = trY
        clf = rf().fit(Xtr, ytr)
        proba = clf.predict_proba(feats([wins[i] for i in te]))[:, 1]
        m = binary_metrics(y[te], (proba >= L2.FALL_PROBA_TH).astype(int)).summary()
        sens.append(m["sensitivity"]); prec.append(m["precision"]); f1.append(m["f1"])
    print(f"  피험자분할 CV(th={L2.FALL_PROBA_TH}): sens {np.mean(sens):.3f} "
          f"prec {np.mean(prec):.3f} F1 {np.mean(f1):.3f}")

    # 최종: 전체 데이터 학습(증강 포함)
    if a.aug:
        W, Y, _ = augment_train(wins, list(y), list(g), n_aug=2, seed=0, max_angle_deg=angle)
        Xall = feats(W); yall = Y
    else:
        Xall = feats(wins); yall = y
    final = rf().fit(Xall, yall)

    # 백업 후 저장 — FallModel 규약은 'bare classifier'(fall_proba가 model.predict_proba 직접 호출)
    if out_path.exists():
        shutil.copy2(out_path, str(out_path) + ".bak")
        print(f"  백업: {out_path}.bak")
    joblib.dump(final, out_path)
    print(f"  저장: {out_path}  (학습 {len(yall)} samples)")


if __name__ == "__main__":
    main()
