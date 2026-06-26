"""L4(안정심박 추세) 실데이터 검증 — Stanford COVID Wearables(120명).

두 가지 정직한 측정(라벨 부재 → L1과 동일 방법론):
 (A) 실 오탐율: 실제 안정심박 일변동에 L4 CUSUM 상승추세 탐지 → person-month당 경보 수
     (대부분 person-day는 정상 → 스팸이면 높고, 특이적이면 낮다. FA 상한.)
 (B) 민감도/리드타임: 실 베이스라인 위에 감염형 상승(+Δbpm 램프)을 주입 →
     탐지율과 리드타임(증상 전 며칠 잡나) 측정. Δ 스윕.

산출 → artifacts/l4_resting_hr_report.json
일일 안정심박은 artifacts/l4_daily_rhr.json 에 캐시(재실행 가속).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L4
from widu.types import RecordSample, RecordKind
from widu.l4_trend import TrendMonitor
from widu.datasets import covid_wearables

DATA = ROOT / "data" / "covid_wearables" / "COVID-19-Wearables"
CACHE = ROOT / "artifacts" / "l4_daily_rhr.json"
DAY = 86400.0


def build_cache(max_p=None) -> dict:
    if CACHE.exists():
        return json.loads(CACHE.read_text(encoding="utf-8"))
    out = {}
    for pid, s in covid_wearables.iter_daily_resting_hr(DATA, max_p=max_p):
        out[pid] = {d.strftime("%Y-%m-%d"): round(float(v), 2) for d, v in s.items()}
        print(f"  {pid}: {len(out[pid])} days  RHR median={np.median(list(out[pid].values())):.0f}")
    CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _series(daymap: dict) -> tuple[list[str], np.ndarray]:
    days = sorted(daymap)
    return days, np.array([daymap[d] for d in days], float)


def detect_episodes(vals: np.ndarray) -> list[int]:
    """일일 안정심박 배열 → uptrend 경보가 발생한 day index 목록(상승에지)."""
    mon = TrendMonitor()
    fired_idx = []
    prev = False
    for i, v in enumerate(vals):
        det = mon.update(RecordSample(i * DAY, RecordKind.RESTING_HR, float(v)))
        cur = det is not None and det.scenario == "resting_hr_uptrend"
        if cur and not prev:
            fired_idx.append(i)
        prev = cur
    return fired_idx


def eval_false_alarm(cache: dict) -> dict:
    total_days = 0
    total_eps = 0
    per_person = []
    for pid, daymap in cache.items():
        if len(daymap) < L4.BASELINE_DAYS + 7:
            continue
        _, vals = _series(daymap)
        eps = detect_episodes(vals)
        total_days += len(vals)
        total_eps += len(eps)
        per_person.append(len(eps) / (len(vals) / 30.0))   # 경보/월
    per_person = np.array(per_person)
    return {
        "participants": int(len(per_person)),
        "person_days": int(total_days),
        "uptrend_episodes": int(total_eps),
        "alerts_per_person_month_mean": round(float(per_person.mean()), 3),
        "alerts_per_person_month_median": round(float(np.median(per_person)), 3),
        "pct_persons_zero_alerts": round(float((per_person == 0).mean() * 100), 1),
        "note": "라벨 부재 → FA 상한(일부는 실제 감염일 수 있음). 낮을수록 특이적.",
    }


def inject_ramp(vals: np.ndarray, onset: int, delta: float,
                ramp=2, sustain=5) -> np.ndarray:
    """onset일부터 +delta bpm 감염형 상승(램프 ramp일→정점 sustain일→점감)."""
    out = vals.astype(float).copy()
    n = len(out)
    for k in range(ramp):
        i = onset + k
        if i < n:
            out[i] += delta * (k + 1) / ramp
    for k in range(sustain):
        i = onset + ramp + k
        if i < n:
            out[i] += delta
    for k in range(ramp):      # 회복 점감
        i = onset + ramp + sustain + k
        if i < n:
            out[i] += delta * (ramp - k - 1) / ramp
    return out


def eval_sensitivity(cache: dict, deltas=(4, 6, 8, 10, 12)) -> dict:
    """실 베이스라인 위 주입 → Δ별 탐지율·리드타임(증상 전 며칠)."""
    rng = np.random.default_rng(0)
    res = {}
    for delta in deltas:
        det_cnt = tot = 0
        leads = []
        for pid, daymap in cache.items():
            _, base = _series(daymap)
            if len(base) < L4.BASELINE_DAYS + 12:
                continue
            # onset = 베이스라인 워밍업 이후 임의일(끝에서 여유 12일)
            onset = int(rng.integers(L4.BASELINE_DAYS + 1, len(base) - 12))
            inj = inject_ramp(base, onset, float(delta))
            eps = detect_episodes(inj)
            # 주입 구간(onset..onset+9) 내 첫 경보
            win = [e for e in eps if onset - 1 <= e <= onset + 9]
            tot += 1
            if win:
                det_cnt += 1
                # 리드: '정점(onset+ramp+sustain≈증상절정)' 대비 며칠 앞 — 여기선 onset 기준 지연
                leads.append(win[0] - onset)
        res[f"delta_{delta}"] = {
            "detect_rate": round(det_cnt / tot, 3) if tot else None,
            "median_days_after_onset": round(float(np.median(leads)), 1) if leads else None,
            "n": tot,
        }
    return res


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("=== 일일 안정심박 캐시 빌드(최초 1회 느림) ===")
    cache = build_cache()
    print(f"참가자 {len(cache)}명 캐시 완료\n")
    fa = eval_false_alarm(cache)
    print("=== (A) 실 오탐율 ===")
    print(json.dumps(fa, ensure_ascii=False, indent=2))
    sens = eval_sensitivity(cache)
    print("\n=== (B) 주입 민감도/리드타임 ===")
    print(json.dumps(sens, ensure_ascii=False, indent=2))
    report = {"false_alarm": fa, "sensitivity_injection": sens,
              "params": {"RESTING_HR_DELTA": L4.RESTING_HR_DELTA,
                         "CUSUM_K": L4.CUSUM_K, "CUSUM_H": L4.CUSUM_H,
                         "BASELINE_DAYS": L4.BASELINE_DAYS}}
    out = ROOT / "artifacts" / "l4_resting_hr_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
