"""중간지평 '넘어진 뒤 미회복' 안전망 검증 (실 SisFall + 사후 정지 시뮬).

목적: L2(충격 분류)가 놓친 고령 낙상을, 충격 후 미회복(무활동)으로 잡는지 + 오탐.
방법: 실 파일을 충격 시점까지 먹인 뒤 '가만히 누움'을 시간 전진시켜 주입.
  - 고령 낙상: fall_unrecovered 발화율(=안전망 회수율)
  - 충격성 ADL(앉기 등 >ARM_G): 발화율(=오탐, 앉고 쉬면 잘못 울리나)
SisFall 녹화가 짧아 실제 미회복 FP율은 POC 필요 — 여기선 '정지 가정'하의 상한.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2, L3
from widu.datasets import sisfall
from widu.preprocess import resample_antialiased, smv
from widu.pipeline import StreamProcessor
from widu.types import IMUSample, AlertLevel
from widu.l2_fall import FallModel


def simulate(arr50: np.ndarray, watch_s: float = 220.0) -> bool:
    """충격 시점까지 실데이터 → 이후 정지 주입 → fall_unrecovered 발화?"""
    sp = StreamProcessor()
    u = "p"
    s = smv(np.column_stack([arr50[:, 0:3], np.zeros((len(arr50), 3))]))
    pk = int(np.argmax(s))
    end = min(len(arr50), pk + 5)
    t = 0.0
    for i in range(end):                       # 실 낙상(충격까지)
        sp.ingest_imu(u, IMUSample(t, *arr50[i, 0:3], *arr50[i, 3:6]))
        t += 1 / L2.FS
    fired = False
    # 사후 정지(누움)를 실배포와 같은 50Hz 로 주입(추정기 플러시 2.5s < grace)
    rng = np.random.default_rng(0)
    n = int(watch_s * L2.FS)
    base = np.array([0.10, 0.95, 0.30])        # 누운 자세 — 단, 중력 크기는 ~1g
    base = base / np.linalg.norm(base)
    dt = 1.0 / L2.FS
    for _ in range(n):
        a = base + rng.normal(0, 0.004, 3)     # 누워 미동(동적성분 < REST 임계)
        o = sp.ingest_imu(u, IMUSample(t, a[0], a[1], a[2], *rng.normal(0, 0.01, 3)))
        if o and any(d.scenario == "fall_unrecovered" for d in o.detections):
            fired = True
            break
        t += dt
    return fired


def main():
    root = ROOT / "data" / "SisFall"
    model = FallModel()
    eld_fall, hard_adl = [], []
    for f in sorted(root.rglob("*.txt")):
        if f.name[0].upper() not in ("F", "D"):
            continue
        eld = f.parent.name.upper().startswith("SE")
        arr, lab = sisfall.load_file(f)
        if len(arr) == 0:
            continue
        a = resample_antialiased(arr, sisfall.FS, L2.FS)
        peak = float(smv(np.column_stack([a[:, 0:3], np.zeros((len(a), 3))])).max())
        if lab == 1 and eld and len(eld_fall) < 40:
            eld_fall.append(a)
        # 충격성 ADL(무장 임계 초과) — 오탐 후보
        if lab == 0 and peak >= L3.POST_FALL_ARM_G and len(hard_adl) < 40:
            hard_adl.append(a)

    t0 = time.time()
    rec_rate = np.mean([simulate(a) for a in eld_fall]) if eld_fall else float("nan")
    fp_rate = np.mean([simulate(a) for a in hard_adl]) if hard_adl else float("nan")
    res = {
        "post_fall_watch_sec": L3.POST_FALL_WATCH_SEC,
        "arm_g": L3.POST_FALL_ARM_G,
        "elderly_fall_recover_rate": round(float(rec_rate), 3),
        "hard_adl_false_fire_rate": round(float(fp_rate), 3),
        "n_elderly_fall": len(eld_fall), "n_hard_adl": len(hard_adl),
        "note": "정지 가정하의 상한. 실 미회복 FP는 POC 필요(앉고 쉬는 정상 패턴).",
    }
    (ROOT / "artifacts" / "postfall_validation.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n안전망 회수율(고령 낙상→미회복) {rec_rate:.3f} / 충격ADL 오탐 {fp_rate:.3f}  ({time.time()-t0:.0f}s)")


if __name__ == "__main__":
    main()
