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


# --- 입력 검증: 잘못된 요청은 500 이 아니라 400 으로 (HANDOFF_ISSUES P1-2) --- #
# 핸들러가 필수 필드(KeyError)·잘못된 enum/숫자(ValueError)·null/타입오류(TypeError)에
# 부딪히면 전역적으로 400 + 에러 본문으로 변환한다. 잘못된 JSON 본문은 Flask 가 이미 400.
@app.errorhandler(KeyError)
def _err_missing_field(e):
    return jsonify({"error": "missing_field", "field": str(e).strip("'\"")}), 400


@app.errorhandler(ValueError)
def _err_bad_value(e):
    return jsonify({"error": "bad_value", "detail": str(e)}), 400


@app.errorhandler(TypeError)
def _err_bad_type(e):
    return jsonify({"error": "bad_type", "detail": str(e)}), 400


@app.get("/healthz")
def healthz():
    # 낙상 모델 적재 가능 여부로 readiness 표시. (P1-1: 과거 존재하지 않는 SP._fall_model
    # 참조로 500 → _model_for("watch") 의 적재 결과를 사용하도록 교정.)
    return jsonify({"ok": True, "service": "widu",
                    "fall_model": SP._model_for("watch").trained})


@app.post("/users/<uid>/hr")
def hr(uid):
    d = request.get_json(force=True)
    acc = Accuracy(d.get("accuracy", "UNKNOWN"))
    a = SP.ingest_hr(uid, HRSample(_ts(d), float(d["bpm"]), acc))
    return jsonify(a.to_dict())


@app.post("/users/<uid>/imu")
def imu(uid):
    d = request.get_json(force=True)
    # P1-3: source(watch/phone)를 수용해 위치별 모델(손목/허리) 라우팅을 살린다.
    # 미전달 시 기존 동작 보존(source="watch"). (IMUSample.accuracy 는 현재 파이프라인에서
    # 소비되지 않아 의도적으로 받지 않는다 — HR 의 Accuracy enum 과 혼동 방지.)
    a = SP.ingest_imu(uid, IMUSample(
        _ts(d), float(d["ax"]), float(d["ay"]), float(d["az"]),
        float(d.get("gx", 0)), float(d.get("gy", 0)), float(d.get("gz", 0)),
        source=d.get("source", "watch")))
    return jsonify(a.to_dict() if a else {"status": "ok"})


@app.post("/users/<uid>/native_fall")
def native_fall(uid):
    """네이티브 낙상(애플 CMFallDetectionManager / 삼성 FALL_DETECTED) 위임 라우트.

    body: {source?, confidence?, ts?}. 구현된 StreamProcessor.ingest_fall_event 에 위임
    (HANDOFF_ISSUES P1-4 — 메서드는 있었으나 HTTP 진입점이 없었음).
    """
    d = request.get_json(force=True)
    a = SP.ingest_fall_event(uid, _ts(d), source=d.get("source", "watch"),
                             confidence=float(d.get("confidence", 0.95)))
    return jsonify(a.to_dict())


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
