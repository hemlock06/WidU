"""골든 특성화 테스트 — 리팩토링 안전망.

검증된 현재 동작을 '골든'으로 박제(capture)하고, 리팩토링 후 동일한지 비교(check).
어떤 미세한 행동/특징 변화도 잡아낸다(특징 순서 계약·파이프라인 판정·융합 로직).

  python scripts/golden_check.py capture   # 리팩토링 '전' 1회 — artifacts/golden.json 저장
  python scripts/golden_check.py check     # 리팩토링 '후' — 골든과 diff(불일치 시 종료 1)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.l2_fall import extract_features, FallModel
from widu.l5_fusion import FusionEngine
from widu.pipeline import StreamProcessor
from widu.types import (IMUSample, HRSample, Detection, Assessment,
                        AlertLevel, ActivityContext, Accuracy)
from widu.config import L2

GOLDEN = ROOT / "tests" / "golden.json"   # 회귀 테스트 기준(커밋됨)


def _rest_imu(t):
    return IMUSample(t, 0.0, 0.0, 1.0)


def cases() -> dict:
    """결정적 입력 → 핵심 출력(불변식). 모두 시드/고정."""
    out = {}

    # 1) 특징 계약: 고정 윈도우 → 23개 특징(반올림)
    rng = np.random.default_rng(42)
    win = rng.normal(0, 0.3, (100, 6)); win[50, :3] += [3.0, 3.0, 3.0]
    feat = extract_features(win, L2.FS)
    out["feature_len"] = int(len(feat))
    out["feature_vec"] = [round(float(x), 4) for x in feat]

    # 2) 휴리스틱 폴백 proba(모델 없을 때 결정성)
    fm = FallModel(ROOT / "models" / "__none__.joblib")
    out["heuristic_proba"] = round(fm.fall_proba(feat), 4)

    # 3) 파이프라인: 하드충격 + 무활동 → fall_long_lie EMERGENCY
    sp = StreamProcessor(); u = "g"; t = 0.0; dt = 1 / 50
    for _ in range(120): sp.ingest_imu(u, _rest_imu(t)); t += dt
    for _ in range(3): sp.ingest_imu(u, IMUSample(t, 4.0, 2.0, 2.0)); t += dt
    fired = None
    for _ in range(500):
        a = sp.ingest_imu(u, IMUSample(t, 0, 0, 1.0 + 0.001)); t += dt
        if a and a.level == AlertLevel.EMERGENCY and fired is None:
            fired = a.detections[0].scenario
    out["fall_hard_immobile"] = fired

    # 4) self-check: 의심 무장 → 45초 무응답 → no_response_fall
    sp2 = StreamProcessor(); u2 = "g2"; t = 0.0
    for _ in range(150): sp2.ingest_imu(u2, _rest_imu(t)); t += dt
    sp2._state(u2).pending_check = (t, "fall_suspected")
    nr = None
    for _ in range(int(50 / dt)):
        a = sp2.ingest_imu(u2, _rest_imu(t)); t += dt
        if a and any(d.scenario == "no_response_fall" for d in a.detections):
            nr = True; break
    out["selfcheck_timeout"] = bool(nr)

    # 5) respond_ok 취소
    sp3 = StreamProcessor(); u3 = "g3"; t = 0.0
    for _ in range(150): sp3.ingest_imu(u3, _rest_imu(t)); t += dt
    sp3._state(u3).pending_check = (t, "fall_suspected")
    for _ in range(int(20 / dt)): sp3.ingest_imu(u3, _rest_imu(t)); t += dt
    sp3.respond_ok(u3, t)
    esc = False
    for _ in range(int(40 / dt)):
        a = sp3.ingest_imu(u3, _rest_imu(t)); t += dt
        if a and any(d.scenario == "no_response_fall" for d in a.detections): esc = True
    out["respond_ok_cancels"] = (not esc)

    # 6) L5 융합 판정
    def fuse(dets):
        fe = FusionEngine()
        for d in dets: fe.submit(d)
        a = fe.assess(dets[0].ts + 1, ActivityContext.REST)
        return f"{a.level.name}/{a.escalation}"
    ts = 100.0
    out["fuse_immobility_alone"] = fuse([Detection("L3", AlertLevel.EMERGENCY, "immobility_12h", 0.9, ts)])
    out["fuse_immobility_hr"] = fuse([Detection("L3", AlertLevel.EMERGENCY, "immobility_12h", 0.9, ts),
                                      Detection("L1", AlertLevel.CAUTION, "hr_high", 0.7, ts)])
    out["fuse_suspected"] = fuse([Detection("L2", AlertLevel.CAUTION, "fall_suspected", 0.2, ts)])

    # 7) L0 급성 서맥/빈맥(맥락 REST)
    from widu.l0_safety import L0Safety
    def l0_sustain(bpm):
        l0 = L0Safety(); det = None
        for i in range(60):
            d = l0.update(HRSample(i * 2.0, bpm, Accuracy.HIGH), ActivityContext.REST)
            if d: det = d.scenario
        return det
    out["l0_brady35"] = l0_sustain(35.0)
    out["l0_tachy160"] = l0_sustain(160.0)
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    (ROOT / "artifacts").mkdir(exist_ok=True)
    cur = cases()
    if mode == "capture":
        GOLDEN.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[golden 박제] {len(cur)}개 케이스 → {GOLDEN}")
        for k, v in cur.items():
            if k != "feature_vec":
                print(f"  {k}: {v}")
        return
    if not GOLDEN.exists():
        print("골든 없음 — 먼저 'capture' 실행"); sys.exit(2)
    gold = json.loads(GOLDEN.read_text(encoding="utf-8"))
    diffs = []
    for k in sorted(set(gold) | set(cur)):
        if gold.get(k) != cur.get(k):
            diffs.append((k, gold.get(k), cur.get(k)))
    if not diffs:
        print(f"✅ 골든 일치 — {len(cur)}개 케이스 전부 동일(동작 불변 확인)")
        return
    print(f"❌ 불일치 {len(diffs)}건:")
    for k, g, c in diffs:
        if k == "feature_vec":
            gd = sum(1 for a, b in zip(g, c) if a != b)
            print(f"  {k}: {gd}개 특징 값 변경(특징 계약 깨짐!)")
        else:
            print(f"  {k}: 골든={g} → 현재={c}")
    sys.exit(1)


if __name__ == "__main__":
    main()
