"""VitalDB 오픈 API 클라이언트 — 심혈관/호흡 생리적 타당성·임계 보정.

출처: https://vitaldb.net (CC BY 4.0), PhysioNet, AWS Open Data.
WIDYU 팀이 이미 시작(SCRUM-76 'VitalDB 데이터셋 샘플링').
주의: 수술/ICU 데이터 → 손목 PPG 와 도메인 갭. '직접 배포 모델'이 아니라
      임계 보정·생리적 범위 확인·심혈관 이벤트 세그먼트 추출용.

Web API (HTTP GET):
  https://api.vitaldb.net/trks    → 트랙 목록 CSV (caseid,tname,tid)
  https://api.vitaldb.net/cases   → 임상정보 CSV
  https://api.vitaldb.net/{tid}   → 해당 트랙 데이터 CSV (Time,value)
"""
from __future__ import annotations

import io
from typing import List

BASE = "https://api.vitaldb.net"


def _get_csv(url: str):
    import gzip
    import requests
    import pandas as pd
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    data = r.content
    if data[:2] == b"\x1f\x8b":            # gzip 매직 → 압축 해제(VitalDB API는 GZip CSV)
        data = gzip.decompress(data)
    return pd.read_csv(io.BytesIO(data))


def list_tracks():
    """전체 트랙 목록 (caseid, tname, tid)."""
    return _get_csv(f"{BASE}/trks")


def list_cases():
    """임상 메타 (caseid, age, sex, dx, ...)."""
    return _get_csv(f"{BASE}/cases")


def find_tracks(tname_contains: str, tracks=None):
    """이름에 특정 문자열을 포함하는 트랙(예: 'SPO2','HR','ECG_II','ART')."""
    df = tracks if tracks is not None else list_tracks()
    return df[df["tname"].str.contains(tname_contains, case=False, na=False)]


def load_track(tid: str):
    """단일 트랙 시계열 CSV → DataFrame(Time, value)."""
    return _get_csv(f"{BASE}/{tid}")


def sample_signal_segment(tname: str = "Solar8000/HR",
                          n_cases: int = 3) -> List:
    """대표 트랙 몇 개를 받아 (caseid, DataFrame) 리스트로.

    네트워크가 필요. 오프라인이면 빈 리스트.
    """
    out = []
    try:
        trks = list_tracks()
    except Exception as e:  # 네트워크/패키지 부재
        print(f"[vitaldb] 트랙 목록 실패: {e}")
        return out
    cand = find_tracks(tname, trks).head(n_cases)
    for _, row in cand.iterrows():
        try:
            df = load_track(row["tid"])
            out.append((row["caseid"], df))
        except Exception as e:
            print(f"[vitaldb] {row['tid']} 실패: {e}")
    return out
