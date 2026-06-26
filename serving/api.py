"""WidU 서빙 API — 배포본(SCRUM-287 /check)의 다계층 후계.

Flask. 워치/앱/서버가 신호를 POST 하면 융합 판단(3-상태 + 에스컬레이션)을 반환.
실행:  python serving/api.py   (기본 0.0.0.0:5001)
엔드포인트:
  POST /users/<uid>/hr        {ts,bpm,accuracy}
  POST /users/<uid>/imu       {ts,ax,ay,az,gx,gy,gz}
  POST /users/<uid>/location  {ts,lat,lon}
  POST /users/<uid>/record    {ts,kind,value}
  POST /users/<uid>/safezones {zones:[[lat,lon,radius], ...]}
  GET  /users/<uid>/status
  GET  /healthz
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flask import Flask, request, jsonify

from widu.pipeline import StreamProcessor
from widu.types import (HRSample, IMUSample, LocSample, RecordSample,
                        Accuracy, RecordKind)

app = Flask(__name__)
# 능동학습 수집: 환경변수 WIDU_COLLECT=1 + 사용자 동의 시에만 활성(프라이버시 기본 off).
SP = StreamProcessor(collect_data=os.environ.get("WIDU_COLLECT") == "1")


def _ts(d):
    return float(d.get("ts") or time.time())


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "service": "widu", "fall_model": SP._fall_model.trained})


@app.post("/users/<uid>/hr")
def hr(uid):
    d = request.get_json(force=True)
    acc = Accuracy(d.get("accuracy", "UNKNOWN"))
    a = SP.ingest_hr(uid, HRSample(_ts(d), float(d["bpm"]), acc))
    return jsonify(a.to_dict())


@app.post("/users/<uid>/imu")
def imu(uid):
    d = request.get_json(force=True)
    a = SP.ingest_imu(uid, IMUSample(
        _ts(d), float(d["ax"]), float(d["ay"]), float(d["az"]),
        float(d.get("gx", 0)), float(d.get("gy", 0)), float(d.get("gz", 0))))
    return jsonify(a.to_dict() if a else {"status": "ok"})


@app.post("/users/<uid>/location")
def location(uid):
    d = request.get_json(force=True)
    a = SP.ingest_location(uid, LocSample(_ts(d), float(d["lat"]), float(d["lon"]),
                                          d.get("speed")))
    return jsonify(a.to_dict() if a else {"status": "ok"})


@app.post("/users/<uid>/record")
def record(uid):
    d = request.get_json(force=True)
    a = SP.ingest_record(uid, RecordSample(_ts(d), RecordKind(d["kind"]), float(d["value"])))
    return jsonify(a.to_dict() if a else {"status": "ok"})


@app.post("/users/<uid>/safezones")
def safezones(uid):
    d = request.get_json(force=True)
    SP.set_safe_zones(uid, [tuple(z) for z in d["zones"]])
    return jsonify({"status": "ok", "count": len(d["zones"])})


@app.get("/users/<uid>/status")
def status(uid):
    return jsonify(SP.status(uid).to_dict())


# --- 능동학습: 응답/확인이 곧 라벨(배포=실데이터 엔진) --- #
@app.post("/users/<uid>/respond_ok")
def respond_ok(uid):
    """사용자가 self-check에 '괜찮아요' → 격상 취소 + 라벨=오경보."""
    d = request.get_json(force=True, silent=True) or {}
    a = SP.respond_ok(uid, _ts(d))
    return jsonify(a.to_dict())


@app.post("/users/<uid>/confirm_incident")
def confirm_incident(uid):
    """가족/사용자 사후 확인 → 라벨 적재. body: {is_fall: bool, by?: str}."""
    d = request.get_json(force=True)
    sid = SP.confirm_incident(uid, bool(d["is_fall"]), by=d.get("by", "guardian"))
    return jsonify({"status": "ok", "sample_id": sid, "labeled": sid is not None})


@app.get("/collector/stats")
def collector_stats():
    return jsonify(SP.collector.stats())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
