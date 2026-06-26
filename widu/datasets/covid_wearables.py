"""Stanford COVID-19 Wearables 로더 (gbsc IPOP public, 120명 Fitbit).

L4(느린 추세) 실데이터 검증용 — 분당 심박+걸음 → '일일 안정심박'(resting HR).
안정심박 상승추세 = 감염 조기경보(Stanford RHRAD/Mishra 선례)가 L4의 직접 근거.

⚠ 이 공개 릴리스(2023~2024 갱신본)는 증상 발현일 '라벨이 없다'.
   → 라벨 기반 리드타임 대신: 실 안정심박으로 '오탐율'(헛경보 스팸 여부)을 측정하고,
     민감도는 실 베이스라인에 감염형 상승을 주입해 측정(L1과 동일한 정직한 방법론).

resting HR 정의(RHRAD 표준): 걸음=0 분의 심박. 일일 안정심박 = 그 날 걸음0 심박의 중앙값.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator, Optional, Tuple

import numpy as np
import pandas as pd

MIN_REST_MIN_PER_DAY = 30   # 하루 최소 안정(걸음0) 분 수 — 미만이면 그 날 제외


def list_participants(root: Path) -> list[str]:
    """기본 hr.csv 가 있는 참가자 ID 목록(longterm 전용은 별도 취급)."""
    ids = set()
    for p in root.glob("*_hr.csv"):
        ids.add(p.name[: -len("_hr.csv")])
    return sorted(ids)


def _read_minutely(path_hr: Path, path_steps: Path) -> Optional[pd.DataFrame]:
    """분당 정렬된 [heartrate, steps] DataFrame(DatetimeIndex). 결측 흡수."""
    hr = pd.read_csv(path_hr, usecols=["datetime", "heartrate"])
    if hr.empty:
        return None
    hr["datetime"] = pd.to_datetime(hr["datetime"], errors="coerce")
    hr = hr.dropna(subset=["datetime"]).set_index("datetime")
    # 분당 평균(원자료가 초단위인 참가자도 있음)
    hr_m = hr["heartrate"].resample("1min").mean()

    steps_m = None
    if path_steps.exists():
        st = pd.read_csv(path_steps, usecols=["datetime", "steps"])
        st["datetime"] = pd.to_datetime(st["datetime"], errors="coerce")
        st = st.dropna(subset=["datetime"]).set_index("datetime")
        steps_m = st["steps"].resample("1min").sum()

    df = pd.DataFrame({"heartrate": hr_m})
    df["steps"] = steps_m.reindex(df.index) if steps_m is not None else np.nan
    return df.dropna(subset=["heartrate"])


def daily_resting_hr(path_hr: Path, path_steps: Path) -> Optional[pd.Series]:
    """일자 -> 안정심박(걸음0 분 심박 중앙값) 시계열. 표본 부족일은 제외.

    걸음 데이터가 없으면(steps 결측) 야간 대용으로 폴백하지 않고 None(엄격).
    """
    df = _read_minutely(path_hr, path_steps)
    if df is None or df["steps"].isna().all():
        return None
    rest = df[df["steps"] == 0]
    if rest.empty:
        return None
    g = rest["heartrate"].groupby(rest.index.normalize())
    daily = g.median()
    counts = g.size()
    daily = daily[counts >= MIN_REST_MIN_PER_DAY]
    daily = daily.dropna()
    return daily if len(daily) >= 7 else None


def iter_daily_resting_hr(root: Path, max_p: Optional[int] = None
                          ) -> Iterator[Tuple[str, pd.Series]]:
    for i, pid in enumerate(list_participants(root)):
        if max_p is not None and i >= max_p:
            break
        s = daily_resting_hr(root / f"{pid}_hr.csv", root / f"{pid}_steps.csv")
        if s is not None:
            yield pid, s
