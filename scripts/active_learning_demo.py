"""능동학습 루프 데모 — 배포=실데이터 엔진.

루프: 이벤트 발생 → 센서 윈도우 캡처 → 사용자/가족 응답이 라벨 → 디스크 적재 →
      (누적분이 충분하면) train_fall_final 데이터에 합쳐 재학습 → 고령 recall 실데이터 개선.

API(serving): POST /users/<uid>/respond_ok(괜찮음=오경보) ·
              POST /users/<uid>/confirm_incident {is_fall} (가족 확인) · GET /collector/stats
활성: StreamProcessor(collect_data=True) 또는 env WIDU_COLLECT=1 (+ 사용자 동의). 기본 off=프라이버시.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.pipeline import StreamProcessor
from widu.types import IMUSample, AlertLevel
from widu.config import L2
from widu.preprocess import extract_window
from widu.l2_fall import extract_features


def stream_fall(sp, u, hard=True):
    t = 0.0; dt = 1.0 / 50
    for _ in range(120):
        sp.ingest_imu(u, IMUSample(t, 0, 0, 1.0)); t += dt
    spike = (4.0, 2.0, 2.0) if hard else (1.6, 0.8, 1.2)
    for _ in range(3):
        sp.ingest_imu(u, IMUSample(t, *spike)); t += dt
    fired = None
    for _ in range(500):
        a = sp.ingest_imu(u, IMUSample(t, 0, 0, 1.0 + np.random.normal(0, 0.01))); t += dt
        if a and a.level == AlertLevel.EMERGENCY and fired is None:
            fired = a.detections[0].scenario
    return fired, t


def main():
    sp = StreamProcessor(collect_data=True)
    # 1) 진짜 낙상 → 가족이 확인
    sc, t = stream_fall(sp, "alice", hard=True)
    sid = sp.confirm_incident("alice", is_fall=True, by="guardian")
    print(f"[alice] 이벤트={sc} → 가족확인 '낙상' → 적재 {sid}")
    # 2) ADL 충격이 의심 발화 → 사용자가 '괜찮아요'
    sc2, t2 = stream_fall(sp, "bob", hard=False)
    sp.respond_ok("bob", t2)
    print(f"[bob] 이벤트={sc2} → 사용자 '괜찮음' → 오경보 라벨")

    print("\n수집 통계:", sp.collector.stats())
    # 3) 루프 닫힘: 수집 → 학습특징
    W, Y, M = sp.collector.load_dataset()
    X = []
    for w in W:
        win = extract_window(np.asarray(w, float), L2.FS, L2.WIN_SEC, pre_frac=0.75)
        if len(win) >= int(L2.WIN_SEC * L2.FS * 0.5):
            X.append(extract_features(win, L2.FS))
    print(f"재학습 준비: 특징행렬 {np.array(X).shape}, 라벨 {Y}")
    print("→ 누적 후 train_fall_final 데이터에 합쳐 재학습 = 실 고령 데이터로 recall 개선")


if __name__ == "__main__":
    main()
