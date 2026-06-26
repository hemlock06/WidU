"""GeoLife GPS Trajectories 1.3 로더 (Microsoft Research Asia, 182명 실 GPS).

L3(위치/행동) 실데이터 검증용 — 실제 사람의 이동 궤적에서 우리 지오펜스·체류·
무활동 임계가 말이 되는지(staypoint=실 체류지, 이탈 이벤트 폭증 없음) 확인.

포맷: Data/<uid>/Trajectory/<ts>.plt
  - 헤더 6줄 스킵, 이후 CSV: lat, lon, 0, alt(ft), days_since_1899-12-30, date, time
  - 좌표 WGS84. 1초~5초 간격(불규칙), 베이징 중심.
GPS에는 '응급' 라벨이 없다 → 이 검증은 recall이 아니라 '결정적 기하의 sanity·보정'.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Tuple

import numpy as np

# GeoLife 시간은 현지(베이징, UTC+8) naive. epoch 변환만 일관되면 상대시간엔 무관.
_BEIJING = timezone.utc  # 상대시간(체류/무활동/야간시) 판정엔 단일 기준이면 충분


def _data_root(root: Path) -> Path:
    """zip 해제 형태가 'Geolife Trajectories 1.3/Data/...' 이든 'Data/...' 이든 흡수."""
    if (root / "Data").is_dir():
        return root / "Data"
    cand = list(root.glob("**/Data"))
    if cand:
        return sorted(cand, key=lambda p: len(p.parts))[0]
    return root


def list_users(root: Path) -> List[str]:
    d = _data_root(root)
    return sorted([p.name for p in d.iterdir() if p.is_dir() and (p / "Trajectory").is_dir()])


def _parse_plt(path: Path) -> np.ndarray:
    """한 .plt → (N,3) [epoch_sec, lat, lon]. 손상 줄은 건너뜀."""
    out = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for _ in range(6):              # 헤더 6줄
            f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 7:
                continue
            try:
                lat = float(parts[0]); lon = float(parts[1])
                dt = datetime.strptime(parts[5] + " " + parts[6], "%Y-%m-%d %H:%M:%S")
                ts = dt.replace(tzinfo=_BEIJING).timestamp()
            except (ValueError, IndexError):
                continue
            # 베이징 영역 위경도 sanity(이상치 제거)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            out.append((ts, lat, lon))
    return np.array(out, dtype=float) if out else np.empty((0, 3))


def load_user(root: Path, uid: str) -> np.ndarray:
    """사용자 1인의 전 궤적을 시간순 (N,3) [epoch, lat, lon] 으로 병합."""
    traj_dir = _data_root(root) / uid / "Trajectory"
    arrs = [_parse_plt(p) for p in sorted(traj_dir.glob("*.plt"))]
    arrs = [a for a in arrs if len(a)]
    if not arrs:
        return np.empty((0, 3))
    m = np.vstack(arrs)
    return m[np.argsort(m[:, 0])]


def iter_users(root: Path, max_users: int | None = None) -> Iterator[Tuple[str, np.ndarray]]:
    for i, uid in enumerate(list_users(root)):
        if max_users is not None and i >= max_users:
            break
        arr = load_user(root, uid)
        if len(arr):
            yield uid, arr
