"""L3(위치/행동) 실데이터 검증 — GeoLife 1.3 실 GPS 궤적(182명).

GPS엔 '응급' 라벨이 없다 → recall이 아니라 결정적 기하의 'sanity·보정':
 1) staypoint 표준탐지(Li 2008, 반경 50m·체류 10분=우리 config) → 실 체류지 추출이 되나
 2) 최다 체류지 = 집(안전구역 proxy) 으로 두고 우리 지오펜스 로직 가동
 3) 측정: 사용자당 staypoint 수, 안전구역 이탈(INFO) 빈도, 야간배회(CAUTION) 빈도
    → 이탈이 '하루 몇 회' 수준의 상식적 빈도인가, 야간배회가 드물게(특이적) 뜨는가.
산출 → artifacts/l3_geolife_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L3
from widu.types import LocSample
from widu.l3_behavior import BehaviorMonitor, haversine_m
from widu.datasets import geolife

DATA = ROOT / "data" / "geolife"
MIN_POINTS = 2000        # 너무 희소한 사용자 제외
MAX_USERS = 50
CAP_POINTS = 120_000     # 사용자당 포인트 상한(초과 시 균등 서브샘플 ~10s 해상도)


def _decimate(arr: np.ndarray) -> np.ndarray:
    if len(arr) <= CAP_POINTS:
        return arr
    stride = int(np.ceil(len(arr) / CAP_POINTS))
    return arr[::stride]


def staypoints(arr: np.ndarray, dist_th=L3.STAYPOINT_RADIUS_M,
               time_th=L3.STAYPOINT_MIN_SEC):
    """Li 2008 표준 staypoint 탐지. arr=(N,3)[ts,lat,lon] 시간순.
    반환: [(lat,lon,t_in,t_out,dwell_s)]."""
    sps = []
    n = len(arr)
    i = 0
    while i < n - 1:
        j = i + 1
        while j < n:
            d = haversine_m(arr[i, 1], arr[i, 2], arr[j, 1], arr[j, 2])
            if d > dist_th:
                break
            j += 1
        dwell = arr[j - 1, 0] - arr[i, 0]
        if dwell >= time_th and (j - 1) > i:
            lat = float(arr[i:j, 1].mean()); lon = float(arr[i:j, 2].mean())
            sps.append((lat, lon, float(arr[i, 0]), float(arr[j - 1, 0]), float(dwell)))
            i = j
        else:
            i += 1
    return sps


def pick_home(sps, merge_m=120.0):
    """staypoint 군집 중 총 체류시간 최대 = 집(안전구역 proxy). (lat,lon) 반환."""
    if not sps:
        return None
    clusters = []   # [lat,lon,total_dwell,count]
    for (lat, lon, _, _, dw) in sps:
        for c in clusters:
            if haversine_m(lat, lon, c[0], c[1]) <= merge_m:
                tot = c[2] + dw
                c[0] = (c[0] * c[2] + lat * dw) / tot
                c[1] = (c[1] * c[2] + lon * dw) / tot
                c[2] = tot; c[3] += 1
                break
        else:
            clusters.append([lat, lon, dw, 1])
    home = max(clusters, key=lambda c: c[2])
    return (home[0], home[1])


def eval_user(arr: np.ndarray) -> dict | None:
    sps = staypoints(arr)
    home = pick_home(sps)
    if home is None:
        return None
    span_days = (arr[-1, 0] - arr[0, 0]) / 86400.0
    if span_days < 1:
        return None
    mon = BehaviorMonitor()
    mon.set_safe_zones([(home[0], home[1], 100.0)])   # 집+근거리 100m 안전구역
    # ★이벤트=전이(에피소드). update_location은 밖에 있는 매 샘플마다 발화 →
    #   같은 시나리오의 '상승에지'만 1건으로 센다(실시스템 L5 dedup/budget과 동일 취지).
    episodes = {"safezone_exit": 0, "wandering_night": 0}
    prev = None
    for ts, lat, lon in arr:
        det = mon.update_location(LocSample(float(ts), float(lat), float(lon)))
        cur = det.scenario if det is not None else None
        if cur is not None and cur != prev:
            episodes[cur] = episodes.get(cur, 0) + 1
        prev = cur
    return {
        "points": int(len(arr)),
        "span_days": round(span_days, 1),
        "staypoints": len(sps),
        "staypoints_per_day": round(len(sps) / max(span_days, 1), 2),
        "exit_events": episodes["safezone_exit"],
        "exit_per_day": round(episodes["safezone_exit"] / max(span_days, 1), 2),
        "wander_night_events": episodes["wandering_night"],
    }


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    rows = []
    for uid, arr in geolife.iter_users(DATA, max_users=MAX_USERS):
        if len(arr) < MIN_POINTS:
            continue
        arr = _decimate(arr)
        print(f"  [proc] user {uid}: {len(arr)} pts ...", flush=True)
        r = eval_user(arr)
        if r:
            rows.append((uid, r))
            print(f"  user {uid}: {r['span_days']}d  sp={r['staypoints']}"
                  f"({r['staypoints_per_day']}/d)  exit/d={r['exit_per_day']}"
                  f"  night_wander={r['wander_night_events']}", flush=True)
    if not rows:
        print("적격 사용자 없음"); return
    sp_pd = np.array([r["staypoints_per_day"] for _, r in rows])
    ex_pd = np.array([r["exit_per_day"] for _, r in rows])
    nw = np.array([r["wander_night_events"] for _, r in rows])
    summary = {
        "users_evaluated": len(rows),
        "staypoints_per_day_median": round(float(np.median(sp_pd)), 2),
        "exit_per_day_median": round(float(np.median(ex_pd)), 2),
        "exit_per_day_p90": round(float(np.percentile(ex_pd, 90)), 2),
        "users_with_zero_night_wander": int((nw == 0).sum()),
        "night_wander_total": int(nw.sum()),
        "interpretation": "이탈/일이 상식범위(≈1~수회)면 지오펜스 임계 타당. "
                          "야간배회가 대부분 0이면 특이성 OK(드물게만 발화).",
    }
    print("\n=== L3 GeoLife 요약 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out = ROOT / "artifacts" / "l3_geolife_report.json"
    out.write_text(json.dumps({"summary": summary,
                               "per_user": {u: r for u, r in rows}},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[saved] {out}")


if __name__ == "__main__":
    main()
