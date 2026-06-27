"""self-check 임계(FALL_PROBA_SOFT) 최적화 — 시스템 recall ↔ 프롬프트 트레이드오프.

잔여 31%(저충격 소프트폴)를 줄이려 soft를 낮추면 recall↑·ADL 프롬프트↑.
과적합 방지: 단일셋 아니라 LODO(held-out 3셋) 평균으로 knee 선택.
빠른 해석모델(스트리밍 동등): 못 일어난 낙상(무활동+무응답) 시나리오에서
  caught = (proba>=soft → self-check 45초 무응답) OR (impact>=2.5g → L3/캐스케이드)
  prompt(UX) = ADL 중 proba>=soft 비율(=self_check 프롬프트)
산출 → artifacts/selfcheck_sweep_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from widu.config import L2
from widu.l2_fall import _smv
from widu.datasets import weda, umafall, smartfallmm as smm
from widu.falleval import cache_windows, feats, rf, DATA   # 공유 헬퍼(DRY)

ARM_G = 2.5      # L3 fall_unrecovered 무장 충격(POST_FALL_ARM_G) = 비분류기 복구 하한
SOFTS = [0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25]


def cache(gen, fs):
    """→ (X feats, y, impact_max). cache_windows 와 동일 전처리 + 윈도우별 최대 충격."""
    w = cache_windows(gen, fs)
    X = feats([x for x, _, _ in w])
    y = np.array([l for _, l, _ in w])
    im = np.array([float(_smv(np.asarray(x, float)[:, :3]).max()) for x, _, _ in w])
    return X, y, im


def main():
    (ROOT / "artifacts").mkdir(exist_ok=True)
    print("LODO 손목 3셋 캐시...", flush=True)
    sources = {
        "WEDA": cache(weda.iter_dataset(DATA / "WEDA_raw"), weda.FS),
        "UMAFall": cache(umafall.iter_dataset(DATA / "UMAFall_raw", "WRIST"), umafall.FS),
        "SmartFallMM": cache(smm.iter_dataset(DATA / "SmartFallMM", "young", "watch"), smm.FS),
    }
    # 고령 ADL(프롬프트 비용 평가에 포함 — 실제 타깃 일상)
    Xo, yo, imo = cache(smm.iter_dataset(DATA / "SmartFallMM", "old", "watch"), smm.FS)
    eld = (Xo[yo == 0], imo[yo == 0])
    names = list(sources)

    # held-out 별 proba 산출
    per = {}
    for held in names:
        Xtr = np.vstack([sources[n][0] for n in names if n != held])
        ytr = np.concatenate([sources[n][1] for n in names if n != held])
        clf = rf().fit(Xtr, ytr)
        Xh, yh, imh = sources[held]
        pr = clf.predict_proba(Xh)[:, 1]
        per[held] = {"proba": pr, "y": yh, "impact": imh,
                     "eld_proba": clf.predict_proba(eld[0])[:, 1]}

    rows = {}
    for soft in SOFTS:
        recs, prompts, eld_prompts = [], [], []
        for held in names:
            d = per[held]
            fall = d["y"] == 1
            caught = (d["proba"][fall] >= soft) | (d["impact"][fall] >= ARM_G)
            recs.append(float(caught.mean()))
            adl = d["y"] == 0
            prompts.append(float((d["proba"][adl] >= soft).mean()))
            eld_prompts.append(float((d["eld_proba"] >= soft).mean()))
        rows[f"{soft:.2f}"] = {
            "system_recall_unrecovered": round(float(np.mean(recs)), 3),
            "adl_prompt_rate": round(float(np.mean(prompts)), 3),
            "elderly_adl_prompt_rate": round(float(np.mean(eld_prompts)), 3),
        }
    print("\nsoft  시스템recall  ADL프롬프트  고령ADL프롬프트")
    for s, r in rows.items():
        print(f"{s}    {r['system_recall_unrecovered']:.3f}        "
              f"{r['adl_prompt_rate']:.3f}        {r['elderly_adl_prompt_rate']:.3f}")
    out = {"current_soft": L2.FALL_PROBA_SOFT, "arm_g": ARM_G, "sweep": rows,
           "note": "recall=못 일어난 낙상(무활동+무응답) 시나리오. LODO 3셋 평균(과적합 방지). "
                   "프롬프트=오경보 아님(응답시 해제). 고령 ADL 프롬프트가 실 UX 비용에 가까움."}
    (ROOT / "artifacts" / "selfcheck_sweep_report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n[saved] artifacts/selfcheck_sweep_report.json")


if __name__ == "__main__":
    main()
