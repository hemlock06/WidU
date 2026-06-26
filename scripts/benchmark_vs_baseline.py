"""머리맞대 벤치마크 — WIDYU-ai(원본) vs WidU(L0+L1).

원본(app.py 그대로): 최근 15개 HR의 MA±2σ 밖(국소이상치) AND 고정 band(≥100 or ≤80) → 1.
  ★상태없음·맥락없음·HR만. 두 조건 AND → 점진 악화는 MA가 추종해 outlier 실패 = 미탐 예상.
WidU: L0(임상 하드바운드<40/>150/<25 + 안정맥락>130, 지속) + L1(개인 baseline·맥락·3분지속·안정시).

측정:
 (1) 오경보율: PPG-DaLiA 실데이터(건강 15명) → 두 시스템 알람 에피소드/시간(건강=전부 오탐).
 (2) 응급 탐지: 합성 스트림에 급성/점진 서맥·빈맥·안정빈맥 주입 → 탐지여부·지연.
산출 → artifacts/benchmark_vs_baseline.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import Activity
from widu.types import HRSample, ActivityContext, Accuracy, AlertLevel
from widu.l0_safety import L0Safety
from widu.l1_hr import PersonalHRModel
from widu.datasets import ppg_dalia

HR_DT, ACC_FS = 2.0, 32.0


# ----------------------------- 원본(WIDYU-ai) ----------------------------- #
def widyu_ai(hr_list, window_size=15, multiplier=2, up=100, lo=80) -> int:
    """app.py 의 check_anomaly 로직 그대로(numpy 고속, pandas rolling std=ddof1 일치).
    최근 window_size 값의 MA±mσ 밖(국소이상치) AND 고정 band(≥up or ≤lo) → 1."""
    if len(hr_list) < window_size:
        return 0
    w = np.asarray(hr_list[-window_size:], float)
    ma = w.mean()
    std = w.std(ddof=1)            # pandas rolling std 와 동일(표본표준편차)
    last = w[-1]
    u, l = ma + multiplier * std, ma - multiplier * std
    return int((last > u or last < l) and (last >= up or last <= lo))


def widyu_stream_alarms(hr):
    """스트림에 원본을 슬라이딩 적용 → 알람 에피소드(상승에지) 인덱스 목록."""
    eps, prev = [], False
    buf = []
    for i, v in enumerate(hr):
        buf.append(float(v))
        if len(buf) > 15:
            buf.pop(0)
        al = widyu_ai(buf) == 1
        if al and not prev:
            eps.append(i)
        prev = al
    return eps


# ----------------------------- WidU(L0+L1) ----------------------------- #
def widu_stream_alarms(hr, ctxs):
    l0, l1 = L0Safety(), PersonalHRModel()
    eps, prev = [], False
    for i, (v, c) in enumerate(zip(hr, ctxs)):
        s = HRSample(i * HR_DT, float(v), Accuracy.HIGH)
        ctx = ActivityContext(c)
        d0 = l0.update(s, ctx)
        d1 = l1.update(s, ctx)
        al = (d0 is not None) or (d1 is not None and d1.level in
                                  (AlertLevel.CAUTION, AlertLevel.EMERGENCY))
        if al and not prev:
            eps.append(i)
        prev = al
    return eps


def acc_ctx(win):
    sma = float(np.abs(np.sqrt((win ** 2).sum(1)) - 1.0).mean())
    return "REST" if sma < Activity.SMA_REST else ("LOW" if sma < Activity.SMA_LOW else "ACTIVE")


# ----------------------------- (1) 오경보율 ----------------------------- #
def false_alarm_rate():
    root = ROOT / "data" / "PPG_DaLiA"
    if not (root.exists() and any(root.rglob("S*.pkl"))):
        return {"error": "PPG-DaLiA 미발견"}
    w_eps = u_eps = 0
    tot_h = 0.0
    for subj, acc, hr, act in ppg_dalia.iter_dataset(root):
        n = len(hr)
        ctxs = []
        for i in range(n):
            s = int(i * HR_DT * ACC_FS)
            win = acc[s:s + int(HR_DT * ACC_FS)]
            ctxs.append(acc_ctx(win) if len(win) >= 8 else "UNKNOWN")
        w_eps += len(widyu_stream_alarms(hr))
        u_eps += len(widu_stream_alarms(hr, ctxs))
        tot_h += n * HR_DT / 3600.0
    return {"hours": round(tot_h, 1),
            "widyu_ai_fp_per_hour": round(w_eps / tot_h, 2), "widyu_ai_episodes": w_eps,
            "widu_fp_per_hour": round(u_eps / tot_h, 2), "widu_episodes": u_eps}


# ----------------------------- (2) 응급 탐지 ----------------------------- #
def make_stream(kind):
    """REST 맥락 합성 HR 스트림. 0~300s 정상(70), 이후 응급 주입(600s)."""
    rng = np.random.default_rng(0)
    base_n, ev_n = 150, 300        # 2s 간격 → 300s 정상 + 600s 이벤트
    base = 70 + rng.normal(0, 2, base_n)
    if kind == "sudden_brady":
        ev = np.full(ev_n, 35.0)
    elif kind == "gradual_brady":
        ev = np.concatenate([np.linspace(70, 35, ev_n // 2), np.full(ev_n - ev_n // 2, 35.0)])
    elif kind == "sudden_tachy":
        ev = np.full(ev_n, 160.0)
    elif kind == "gradual_tachy":
        ev = np.concatenate([np.linspace(70, 160, ev_n // 2), np.full(ev_n - ev_n // 2, 160.0)])
    elif kind == "resting_tachy":
        ev = np.full(ev_n, 135.0)
    else:
        ev = np.full(ev_n, 70.0)
    hr = np.concatenate([base, ev + rng.normal(0, 1.5, ev_n)])
    return hr, base_n


def detect_latency(eps, onset_idx):
    after = [e for e in eps if e >= onset_idx - 1]
    return round((after[0] - onset_idx) * HR_DT, 0) if after else None


def emergency_detection():
    res = {}
    for kind in ["sudden_brady", "gradual_brady", "sudden_tachy",
                 "gradual_tachy", "resting_tachy"]:
        hr, onset = make_stream(kind)
        ctxs = ["REST"] * len(hr)
        w = widyu_stream_alarms(hr)
        u = widu_stream_alarms(hr, ctxs)
        res[kind] = {
            "widyu_ai": {"detected": detect_latency(w, onset) is not None,
                         "latency_s": detect_latency(w, onset)},
            "widu": {"detected": detect_latency(u, onset) is not None,
                     "latency_s": detect_latency(u, onset)},
        }
    return res


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("=== (1) 실데이터 오경보율 (PPG-DaLiA, 건강 15명) ===", flush=True)
    fa = false_alarm_rate()
    print(json.dumps(fa, ensure_ascii=False, indent=2))
    print("\n=== (2) 응급 탐지/지연 (합성, REST) ===", flush=True)
    ed = emergency_detection()
    for k, v in ed.items():
        print(f"  {k:16s} 원본={'O' if v['widyu_ai']['detected'] else 'X'}"
              f"({v['widyu_ai']['latency_s']}s)  WidU={'O' if v['widu']['detected'] else 'X'}"
              f"({v['widu']['latency_s']}s)")
    out = {"false_alarm": fa, "emergency_detection": ed}
    (ROOT / "artifacts" / "benchmark_vs_baseline.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[saved] artifacts/benchmark_vs_baseline.json")


if __name__ == "__main__":
    main()
