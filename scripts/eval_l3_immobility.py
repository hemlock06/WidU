"""L3 무활동(12h) + 공백리셋 실데이터 검증 — Stanford 걸음 데이터(120명, 수개월).

검증 대상(v0.3 버그픽스): 실제 기기-off 공백(미착용/충전/수면)을 '무활동'으로
오인해 12h 경보를 남발하지 않는가. 진짜 위험(착용중 12h 부동)만 잡는가.

방법: 분당 걸음 → 10분 빈 활동맥락. 걸음>0=이동(active), 걸음0(데이터있음)=정지(rest),
데이터없음=공백(샘플 미도착=update_activity 미호출) → 다음 샘플서 공백리셋 발동.
측정: 12h 무활동 경보 총수. 실 인구에선 ≈0이어야(깨어있으면 12h내 움직임 + 공백리셋).
산출 → artifacts/l3_immobility_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.types import ActivityContext
from widu.l3_behavior import BehaviorMonitor
from widu.config import L3
from widu.datasets import covid_wearables

DATA = ROOT / "data" / "covid_wearables" / "COVID-19-Wearables"
BIN = "10min"
BIN_SEC = 600


def eval_participant(pid: str) -> dict | None:
    df = covid_wearables._read_minutely(DATA / f"{pid}_hr.csv", DATA / f"{pid}_steps.csv")
    if df is None or df["steps"].isna().all():
        return None
    # 10분 빈. ★활동신호(걸음)의 '부재'를 정지가 아니라 '공백'으로 본다(공백리셋이 흡수).
    #   has = 걸음 표본이 그 빈에 존재했나. 없으면 update_activity 미호출(샘플 미도착).
    steps_present = df["steps"].notna()
    has_bin = steps_present.resample(BIN).sum() > 0
    steps_bin = df["steps"].resample(BIN).sum()          # 존재 시 합(없으면 has=False→스킵)
    idx = steps_bin.index
    if len(idx) < 6 * 24:   # 최소 하루
        return None

    mon = BehaviorMonitor()
    alerts = 0
    longest_immobile_h = 0.0
    cur_immobile = 0.0
    gap_count = 0
    last_ts = None
    for t, has in zip(idx, has_bin.values):
        ts = t.value / 1e9   # ns→s epoch
        if not has:
            # 공백(샘플 미도착) — update_activity 미호출(실서빙과 동일)
            continue
        if last_ts is not None and (ts - last_ts) > L3.IMMOBILE_GAP_RESET_SEC:
            gap_count += 1
        moving = steps_bin.loc[t] > 0
        ctx = ActivityContext.ACTIVE if moving else ActivityContext.REST
        det = mon.update_activity(ctx, ts)
        # 추적: 연속 정지시간(공백 제외, 데이터 있는 빈만)
        if moving:
            cur_immobile = 0.0
        else:
            cur_immobile += BIN_SEC / 3600.0
            longest_immobile_h = max(longest_immobile_h, cur_immobile)
        if det is not None and det.scenario == "immobility_12h":
            alerts += 1
        last_ts = ts

    span_days = (idx[-1].value - idx[0].value) / 1e9 / 86400.0
    return {
        "span_days": round(span_days, 1),
        "gap_resets": gap_count,
        "longest_immobile_h_with_data": round(longest_immobile_h, 1),
        "immobility_12h_alerts": alerts,
    }


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    rows = {}
    total_alerts = 0
    total_days = 0.0
    longest_all = []
    for pid in covid_wearables.list_participants(DATA):
        r = eval_participant(pid)
        if r is None:
            continue
        rows[pid] = r
        total_alerts += r["immobility_12h_alerts"]
        total_days += r["span_days"]
        longest_all.append(r["longest_immobile_h_with_data"])
        if r["immobility_12h_alerts"] > 0:
            print(f"  ⚠ {pid}: {r['immobility_12h_alerts']} alerts  "
                  f"longest_immobile={r['longest_immobile_h_with_data']}h")
    longest_all = np.array(longest_all) if longest_all else np.array([0.0])
    summary = {
        "participants": len(rows),
        "total_person_days": round(total_days, 1),
        "total_immobility_12h_alerts": total_alerts,
        "alerts_per_person_year": round(total_alerts / max(total_days / 365.0, 1e-9), 3),
        "longest_immobile_h_median": round(float(np.median(longest_all)), 1),
        "longest_immobile_h_max": round(float(longest_all.max()), 1),
        "interpretation": "실 인구 기대=0 또는 극소(깨어있으면 12h내 이동 + 공백리셋이 미착용 흡수). "
                          "longest_immobile(데이터있는 정지)가 12h 미만이면 공백리셋이 제대로 작동.",
    }
    print("\n=== L3 무활동/공백리셋 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out = ROOT / "artifacts" / "l3_immobility_report.json"
    out.write_text(json.dumps({"summary": summary, "per_participant": rows},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
