"""능동학습 수집기 — 배포를 '실데이터 엔진'으로.

핵심 발상: self-check/알림에 대한 사용자·가족의 응답이 곧 '라벨'이다.
 - 이벤트(낙상의심/회복/확정/무응답) 발생 → 직전 IMU 윈도우 스냅샷(라벨 대기)
 - respond_ok("괜찮아요") → false_alarm,  가족 confirm_incident → fall/false_alarm
 → (센서 윈도우, 라벨) 쌍이 실제 사용자(고령 포함)에게서 누적 → 고령 recall을 실데이터로 개선.

프라이버시: enabled(동의) 시에만 수집. 저장은 IMU 신호+라벨+최소 메타(원좌표·식별자 없음).
저장: root/index.jsonl(메타) + root/windows/<sample_id>.npy((N,6) g·rad/s).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

VALID_LABELS = {"fall", "false_alarm"}


class ActiveLearningCollector:
    """이벤트 윈도우를 캡처하고, 응답 라벨이 오면 디스크에 학습샘플로 적재."""

    def __init__(self, root: Path, enabled: bool = False):
        self.root = Path(root)
        self.enabled = enabled
        self._pending: Dict[str, Tuple[np.ndarray, dict]] = {}   # event_id -> (window, meta)
        if self.enabled:
            (self.root / "windows").mkdir(parents=True, exist_ok=True)

    # --- 캡처(라벨 대기) --- #
    def capture(self, event_id: str, user: str, window: np.ndarray, meta: dict) -> bool:
        """이벤트 직전 IMU 윈도우 스냅샷을 라벨 대기로 보관. 동의 없으면 무시."""
        if not self.enabled or window is None or len(window) == 0:
            return False
        m = dict(meta); m.update(user=user, event_id=event_id,
                                 n_samples=int(len(window)),
                                 captured_at=round(time.time(), 3))
        self._pending[event_id] = (np.asarray(window, float).copy(), m)
        return True

    # --- 라벨 부여(응답) → 적재 --- #
    def label(self, event_id: str, label: str, by: str) -> Optional[str]:
        """대기 이벤트에 라벨을 달아 디스크에 적재. sample_id 반환(없으면 None)."""
        if not self.enabled or label not in VALID_LABELS:
            return None
        item = self._pending.pop(event_id, None)
        if item is None:
            return None
        window, meta = item
        sample_id = f"{event_id}_{label}"
        meta.update(label=label, labeled_by=by,
                    labeled_at=round(time.time(), 3),
                    window_file=f"windows/{sample_id}.npy")
        np.save(self.root / "windows" / f"{sample_id}.npy", window.astype(np.float32))
        with (self.root / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        return sample_id

    def drop(self, event_id: str) -> None:
        """라벨 없이 폐기(예: 더 강한 이벤트로 대체)."""
        self._pending.pop(event_id, None)

    # --- 적재 데이터 로드(재학습용) --- #
    def load_dataset(self):
        """→ (windows: list[(N,6)], labels: list[int 1=fall], metas: list[dict])."""
        idx = self.root / "index.jsonl"
        W, Y, M = [], [], []
        if not idx.exists():
            return W, Y, M
        for line in idx.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            m = json.loads(line)
            wf = self.root / m["window_file"]
            if wf.exists():
                W.append(np.load(wf)); Y.append(1 if m["label"] == "fall" else 0); M.append(m)
        return W, Y, M

    def stats(self) -> dict:
        W, Y, M = self.load_dataset()
        return {"enabled": self.enabled, "pending": len(self._pending),
                "collected": len(Y), "fall": int(sum(Y)),
                "false_alarm": int(len(Y) - sum(Y)),
                "by": {b: sum(1 for m in M if m.get("labeled_by") == b)
                       for b in {m.get("labeled_by") for m in M}} if M else {}}
