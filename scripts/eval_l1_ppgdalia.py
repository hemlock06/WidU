"""L1(개인화 심박) 실데이터 검증 — PPG-DaLiA(실 손목 HR + 활동).

핵심: 피험자는 건강한 사람들이 운동/일상 → 라벨된 '심박 이상' 없음.
따라서 여기서 뜨는 모든 경보 = 오탐(FP). 이걸로 L1의 실세계 오탐률을 측정.
A/B(맥락게이팅의 가치):
  - gated  : 활동맥락 조건부 개인 기준선(우리 L1) — 운동 중 고심박을 정상으로.
  - naive  : 고정 임계(bpm>100 지속) — 맥락 무시(GitHub MA 레포 류).
또한 ① 맥락별 HR 분리(REST<ACTIVE) ② ACC추정맥락 vs 활동라벨 일치 검증.
결과 → artifacts/l1_ppgdalia.json
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

from widu.config import Activity
from widu.types import HRSample, ActivityContext, Accuracy, AlertLevel
from widu.l1_hr import PersonalHRModel
from widu.datasets import ppg_dalia

ACC_FS = 32.0
HR_DT = 2.0      # PPG-DaLiA 라벨 HR 간격(초)
EXERCISE = {"ACTIVE"}


def acc_context(acc_win: np.ndarray) -> str:
    """2초 ACC 윈도우 → 활동맥락(우리 ActivityEstimator 와 동일 SMA 규칙)."""
    smv = np.sqrt((acc_win ** 2).sum(axis=1))
    sma = float(np.abs(smv - 1.0).mean())
    if sma < Activity.SMA_REST:
        return "REST"
    if sma < Activity.SMA_LOW:
        return "LOW"
    return "ACTIVE"


def naive_alerts(hr: np.ndarray) -> int:
    """고정 임계(bpm>100 지속 20s) 경보 에피소드 수(맥락 무시)."""
    th, need = 100.0, int(20 / HR_DT)
    run, eps, prev = 0, 0, False
    for v in hr:
        run = run + 1 if v > th else 0
        cur = run >= need
        if cur and not prev:
            eps += 1
        prev = cur
    return eps


def run_subject(acc, hr, act):
    model = PersonalHRModel()
    n = len(hr)
    act_fs = (len(act) / (n * HR_DT)) if len(act) else 0.0   # 활동라벨 샘플레이트(≈4Hz)
    gated_eps, prev_alert = 0, False
    ctx_pred, ctx_true, exercise_gated_fp = [], [], 0
    for i in range(n):
        s = int(i * HR_DT * ACC_FS)
        win = acc[s:s + int(HR_DT * ACC_FS)]
        ctx = acc_context(win) if len(win) >= 8 else "UNKNOWN"
        ctx_pred.append(ctx)
        if len(act):
            ai = min(len(act) - 1, int(i * HR_DT * act_fs))   # HR(0.5Hz)↔활동(4Hz) 정렬
            ctx_true.append(ppg_dalia.activity_to_context(act[ai]))
        det = model.update(HRSample(i * HR_DT, float(hr[i]), Accuracy.HIGH),
                           ActivityContext(ctx))
        is_alert = det is not None and det.level in (AlertLevel.CAUTION, AlertLevel.EMERGENCY)
        if is_alert and not prev_alert:
            gated_eps += 1
            if ctx == "ACTIVE":
                exercise_gated_fp += 1
        prev_alert = is_alert
    dur_h = n * HR_DT / 3600.0
    # 맥락별 HR 평균(분리도)
    ctx_pred = np.array(ctx_pred); hrn = hr[:n]
    by_ctx = {c: round(float(hrn[ctx_pred == c].mean()), 1) for c in ("REST", "LOW", "ACTIVE")
              if (ctx_pred == c).any()}
    # ACC맥락 vs 라벨 일치(휴식/운동 이분)
    agree = None
    if len(ctx_true):
        ct = np.array(ctx_true)
        rest_pred = (ctx_pred == "REST"); rest_true = (ct == "REST")
        agree = round(float((rest_pred == rest_true).mean()), 3)
    return {
        "dur_h": round(dur_h, 2),
        "gated_fp_episodes": gated_eps,
        "naive_fp_episodes": naive_alerts(hrn),
        "exercise_gated_fp": exercise_gated_fp,
        "hr_by_context": by_ctx,
        "ctx_vs_label_restagree": agree,
    }


def main():
    root = ROOT / "data" / "PPG_DaLiA"
    if not (root.exists() and any(root.rglob("S*.pkl"))):
        print("PPG-DaLiA 미발견."); return
    t0 = time.time()
    subs = {}
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        subs[subj] = run_subject(acc, hr, act)
        print(f"  {subj}: {subs[subj]['dur_h']}h gated_FP={subs[subj]['gated_fp_episodes']} "
              f"naive_FP={subs[subj]['naive_fp_episodes']} HR맥락={subs[subj]['hr_by_context']}")
    tot_h = sum(s["dur_h"] for s in subs.values())
    g = sum(s["gated_fp_episodes"] for s in subs.values())
    nv = sum(s["naive_fp_episodes"] for s in subs.values())
    agr = [s["ctx_vs_label_restagree"] for s in subs.values() if s["ctx_vs_label_restagree"] is not None]
    report = {
        "subjects": len(subs), "total_hours": round(tot_h, 1),
        "gated_FP_per_hour": round(g / tot_h, 3), "naive_FP_per_hour": round(nv / tot_h, 3),
        "gated_FP_total": g, "naive_FP_total": nv,
        "ctx_vs_label_restagree_mean": round(float(np.mean(agr)), 3) if agr else None,
        "per_subject": subs,
        "note": "건강 피험자 → 모든 경보=오탐. 맥락게이팅이 운동 오탐을 억제하는지.",
    }
    (ROOT / "artifacts" / "l1_ppgdalia.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== L1 실데이터 오탐(건강 {len(subs)}명, {tot_h:.0f}h, {time.time()-t0:.0f}s) ===")
    print(f"  맥락게이팅 오탐/시간 {report['gated_FP_per_hour']}  vs  고정임계 {report['naive_FP_per_hour']}")
    print(f"  ACC맥락 vs 활동라벨 휴식/운동 일치 {report['ctx_vs_label_restagree_mean']}")


if __name__ == "__main__":
    main()
