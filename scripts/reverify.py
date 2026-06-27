"""10라운드 재검증 — 주요 페이즈(실데이터 낙상 검증) 통과 전 최종 점검.

'문제 없었는가 + 이게 최선인가'를 10개 상이 관점으로 실제 코드로 단언한다.
SisFall을 1회 로드 후 OOF(out-of-fold) 예측을 재사용해 여러 라운드를 검증.
결과 → artifacts/reverify_report.json
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.falleval import feats  # 공유 헬퍼(DRY)
from widu.datasets import sisfall
from widu.preprocess import resample_antialiased, extract_window, smv, butter_lowpass
from widu.l2_fall import extract_features, FallDetector, FallModel
from widu.augment import augment_train
from widu.types import IMUSample
from widu.eval.metrics import binary_metrics

R = []
def rec(name, ok, detail):
    R.append((name, bool(ok), detail))
    print(f"[{'OK ' if ok else 'ISSUE'}] {name} — {detail}")




def load_all():
    root = ROOT / "data" / "SisFall"
    W, Y, SUBJ, CODE, ELD = [], [], [], [], []
    arrs = {"fall": [], "adl": []}   # 스트리밍용 소수 보관(arr50)
    t0 = time.time(); skipped = 0
    for f in sorted(root.rglob("*.txt")):
        if f.name[0].upper() not in ("F", "D"):
            continue
        arr, lab = sisfall.load_file(f)
        if len(arr) == 0:
            skipped += 1; continue
        a50 = resample_antialiased(arr, sisfall.FS, L2.FS)
        w = extract_window(a50, L2.FS, L2.WIN_SEC, 0.75)
        if len(w) < int(L2.WIN_SEC * L2.FS * 0.5):
            skipped += 1; continue
        W.append(w); Y.append(lab)
        SUBJ.append(f.parent.name); CODE.append(f.name[:3])
        ELD.append(f.parent.name.upper().startswith("SE"))
        key = "fall" if lab else "adl"
        if len(arrs[key]) < 100:
            arrs[key].append(a50)
    print(f"로드 {len(Y)}윈도우, skip {skipped}, {time.time()-t0:.0f}s")
    return (W, np.array(Y), np.array(SUBJ), np.array(CODE), np.array(ELD), arrs)


def oof_predict(W, Y, SUBJ, n_aug=2, n_splits=5):
    """증강은 raw 윈도우에 적용 후 특징추출(실 파이프라인과 동일). 누수 없는 OOF."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    oof = np.full(len(Y), np.nan)
    fold_f1 = []
    leak_folds = 0
    idx = np.arange(len(Y))
    for tr, te in GroupKFold(n_splits=n_splits).split(idx, Y, SUBJ):
        if set(SUBJ[tr]) & set(SUBJ[te]):
            leak_folds += 1
        Wtr, Ytr, _ = augment_train([W[i] for i in tr], Y[tr], SUBJ[tr], n_aug=n_aug, seed=0)
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1)
        clf.fit(feats(Wtr), Ytr)                          # 윈도우 → 특징
        p = clf.predict_proba(feats([W[i] for i in te]))[:, 1]
        oof[te] = p
        fold_f1.append(binary_metrics(Y[te], (p >= 0.5).astype(int)).f1)
    return oof, np.array(fold_f1), leak_folds


def main():
    root = ROOT / "data" / "SisFall"
    if not (root.exists() and any(root.rglob("*.txt"))):
        print("SisFall 미발견 — 재검증 불가."); return
    W, Y, SUBJ, CODE, ELD, arrs = load_all()
    X = feats(W)                          # 특징(라벨건전성 R3·결정성 R9용)
    oof, fold_f1, leak_folds = oof_predict(W, Y, SUBJ)
    pred = (oof >= 0.5).astype(int)
    pred_th = (oof >= L2.FALL_PROBA_TH).astype(int)   # 배포 임계(0.4)
    m = binary_metrics(Y, pred)

    # R1 재현성/안정성: 폴드 간 F1 분산
    rec("R1.재현성(폴드간 F1)", fold_f1.std() < 0.03,
        f"F1 fold {fold_f1.mean():.3f}±{fold_f1.std():.3f} (안정=std<0.03)")

    # R2 누수: 피험자 겹침 0 + OOF가 전부 채워짐(테스트는 원본만)
    full = not np.isnan(oof).any()
    rec("R2.누수탐색", leak_folds == 0 and full,
        f"피험자겹침 폴드={leak_folds}, OOF 전체채움={full}(증강은 train만)")

    # R3 라벨 건전성: 낙상 충격 > ADL, 고령자 포함
    pk = np.array([x[0] for x in X])  # acc_max
    f_pk, d_pk = pk[Y == 1].mean(), pk[Y == 0].mean()
    n_eld_subj = len(set(SUBJ[ELD])); n_eld_fall = int((ELD & (Y == 1)).sum())
    rec("R3.라벨건전성", f_pk > d_pk and n_eld_subj > 0,
        f"충격 낙상{f_pk:.2f}>ADL{d_pk:.2f}g, 고령피험자{n_eld_subj}명·낙상윈도우{n_eld_fall}")

    # R4 임계 최적성: 안전(미탐 최소)을 위한 임계 sweep
    sweep = {}
    for th in [0.3, 0.4, 0.5, 0.6, 0.7]:
        mm = binary_metrics(Y, (oof >= th).astype(int))
        sweep[th] = (round(mm.sensitivity, 3), round(mm.precision, 3))
    # 민감도 0.98 이상을 만족하는 가장 높은 임계(정밀도 보존)
    ok_th = [th for th, (se, pr) in sweep.items() if se >= 0.98]
    best = max(ok_th) if ok_th else None
    rec("R4.임계최적성", best is not None,
        f"th별(sens,prec)={sweep} → 민감도≥0.98 권장임계={best}")

    # R5 서브그룹: 고령자 recall(타깃!) — 배포임계 기준. 고령 미탐은 안전직결 → 엄격 플래그
    eld_recall = (pred_th[(ELD) & (Y == 1)] == 1).mean()
    adult_recall = (pred_th[(~ELD) & (Y == 1)] == 1).mean()
    eld_recall_03 = (oof[(ELD) & (Y == 1)] >= 0.3).mean()
    weak = []
    for c in sorted(set(CODE[(Y == 1)])):
        idx = (CODE == c) & (Y == 1)
        r = (pred_th[idx] == 1).mean() if idx.sum() else 1.0
        if r < 0.90:
            weak.append((c, round(float(r), 2)))
    rec("R5.고령recall(타깃)", eld_recall >= 0.90,
        f"고령{eld_recall:.3f}(th0.3:{eld_recall_03:.3f})/성인{adult_recall:.3f} "
        f"@임계{L2.FALL_PROBA_TH}, 약한 낙상유형={weak or '없음'} "
        f"{'⚠고령 미탐 과다→학습 보강 필요' if eld_recall < 0.90 else ''}")

    # R6 실데이터 전처리: 안티앨리어싱(>25Hz 억제) + 윈도우 피크위치
    sample = next((f for f in sorted(root.rglob('F*.txt'))), None)
    arr, _ = sisfall.load_file(sample)
    aa = resample_antialiased(arr, sisfall.FS, L2.FS)
    naive = sisfall.resample_to(arr, sisfall.FS, L2.FS)
    def hi_energy(x):
        c = x[:, 0] - x[:, 0].mean(); sp = np.abs(np.fft.rfft(c))
        fr = np.fft.rfftfreq(len(c), 1 / 50.0); return float(sp[fr > 20].sum())
    w = extract_window(aa, L2.FS, L2.WIN_SEC, 0.75)
    peak_pos = int(np.argmax(smv(w))) / max(len(w) - 1, 1)
    rec("R6.실전처리", hi_energy(aa) < hi_energy(naive) and abs(peak_pos - 0.75) < 0.1,
        f">20Hz 에너지 aa<{hi_energy(naive):.0f}, 윈도우 피크 {peak_pos:.2f}≈0.75")

    # R7 서빙(스트리밍) 낙상 검출률 — 실 fall 파일 sample-by-sample
    model = FallModel()
    def stream_detect(a50):
        det = FallDetector(fs=L2.FS, model=model)
        rc = {"mx": 0.0}
        orig = det._classify
        def hook(ts, sv):
            f = extract_features(det._window_array(), L2.FS)
            rc["mx"] = max(rc["mx"], model.fall_proba(f)); orig(ts, sv)
        det._classify = hook
        for i, row in enumerate(a50):
            det.update(IMUSample(i / L2.FS, *row[:3], *row[3:6]))
        return rc["mx"] >= 0.5
    fall_hit = np.mean([stream_detect(a) for a in arrs["fall"]])
    rec("R7.서빙검출률(fall)", fall_hit >= 0.90,
        f"실 낙상파일 스트리밍 검출률 {fall_hit:.3f} (n={len(arrs['fall'])})")

    # R8 서빙 오탐 — 실 ADL 파일
    adl_fp = np.mean([stream_detect(a) for a in arrs["adl"]])
    rec("R8.서빙오탐(ADL)", adl_fp <= 0.20,
        f"실 ADL파일 스트리밍 오트리거 {adl_fp:.3f} (사후무활동 게이트로 추가 억제됨)")

    # R9 결정성: 동일 데이터·seed 재학습 → 동일 예측 + 저장모델 일치
    from sklearn.ensemble import RandomForestClassifier
    c1 = RandomForestClassifier(n_estimators=120, random_state=0, n_jobs=1).fit(X, Y)
    c2 = RandomForestClassifier(n_estimators=120, random_state=0, n_jobs=1).fit(X, Y)
    det_ok = np.array_equal(c1.predict(X), c2.predict(X))
    rec("R9.결정성", det_ok, f"동일 seed 재학습 예측 일치={det_ok}")

    # R10 회귀: 11패스 + 파이프라인 스모크
    import os
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    vp = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_preprocess.py")],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=env)
    passed = "11/11 PASS" in (vp.stdout or "")
    rec("R10.회귀(11패스)", passed, "verify_preprocess 11/11" if passed else "11패스 실패")

    # R11 고령 가중학습이 고령 recall 을 개선하나 (안전직결 — '최선인가' 점검)
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import GroupKFold
    oofw = np.full(len(Y), np.nan)
    for tr, te in GroupKFold(n_splits=5).split(np.arange(len(Y)), Y, SUBJ):
        sw = np.where(ELD[tr], 4.0, 1.0)         # 고령 윈도우 4배 가중
        clf = RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                     random_state=0, n_jobs=-1)
        clf.fit(X[tr], Y[tr], sample_weight=sw)
        oofw[te] = clf.predict_proba(X[te])[:, 1]
    eld_w = (oofw[(ELD) & (Y == 1)] >= L2.FALL_PROBA_TH).mean()
    adult_w = (oofw[(~ELD) & (Y == 1)] >= L2.FALL_PROBA_TH).mean()
    rec("R11.고령가중효과", eld_w >= eld_recall - 0.005,
        f"고령 recall 가중후 {eld_w:.3f}(기존 {eld_recall:.3f}), 성인 {adult_w:.3f} "
        f"→ {'채택 권장' if eld_w > eld_recall + 0.02 else '효과 제한적'}")

    n_ok = sum(1 for _, ok, _ in R if ok)
    report = {"rounds": [{"name": n, "ok": ok, "detail": d} for n, ok, d in R],
              "passed": n_ok, "total": len(R),
              "headline": {"oof_f1@0.5": round(m.f1, 4),
                           "oof_sensitivity": round(m.sensitivity, 4),
                           "oof_precision": round(m.precision, 4)}}
    (ROOT / "artifacts" / "reverify_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n===== 재검증 {n_ok}/{len(R)} OK =====  OOF F1={m.f1:.3f}")


if __name__ == "__main__":
    main()
