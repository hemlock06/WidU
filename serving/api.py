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
from werkzeug.exceptions import HTTPException, BadRequest

from widu.pipeline import StreamProcessor
from widu.types import (HRSample, IMUSample, LocSample, RecordSample,
                        Accuracy, RecordKind)

app = Flask(__name__)
# 능동학습 수집: 환경변수 WIDU_COLLECT=1 + 사용자 동의 시에만 활성(프라이버시 기본 off).
SP = StreamProcessor(collect_data=os.environ.get("WIDU_COLLECT") == "1")


# --------------------------------------------------------------------------- #
# 입력 검증 (HANDOFF_ISSUES P1-2 — 외과적 버전). WidU 는 운영 서버 대상이라
# "누구 잘못이냐"를 정확히 구분한다:
#   · 잘못된 *입력*(필수필드 누락·숫자/enum 오류)만 명시적으로 400.
#   · 그 외 모든 예외(= 우리 코드 버그)는 errorhandler(Exception) 가 500.
# 전역으로 KeyError/ValueError/TypeError 를 400 으로 싸잡지 않는다 — 내부 버그가
# 400 으로 위장돼 운영 모니터링(500 감시)에서 사라지는 것을 막기 위함.
# --------------------------------------------------------------------------- #
def _require(d, *keys):
    if not isinstance(d, dict):
        raise BadRequest("body must be a JSON object")
    missing = [k for k in keys if k not in d]
    if missing:
        raise BadRequest("missing field(s): " + ", ".join(missing))


def _num(d, key, default=None):
    """필드를 float 로 파싱. 잘못된 값이면 400. (필수 여부는 _require 로 별도 보장.)"""
    v = d.get(key, default)
    try:
        return float(v)
    except (TypeError, ValueError):
        raise BadRequest("field '%s' must be a number" % key)


def _enum(cls, value, field):
    try:
        return cls(value)
    except ValueError:
        raise BadRequest("invalid %s: %r" % (field, value))


def _ts(d):
    raw = d.get("ts")
    if raw is None or raw == "":
        return time.time()
    try:
        return float(raw)
    except (TypeError, ValueError):
        raise BadRequest("field 'ts' must be a number")


@app.errorhandler(HTTPException)
def _http_err(e):
    # 잘못된 입력/라우팅 등 — 원래 상태코드(400/404/405/415 …) 유지, JSON 본문으로.
    return jsonify({"error": e.name, "detail": e.description}), e.code


@app.errorhandler(Exception)
def _internal_err(e):
    # 여기 도달 = '우리 코드 버그' → 500. 입력오류는 위 HTTPException 핸들러가 이미 400.
    # 운영 모니터링이 500 을 감지하도록 절대 400 으로 가리지 않는다. 상세는 로그로만.
    app.logger.exception("internal error")
    return jsonify({"error": "internal_error"}), 500


@app.get("/healthz")
def healthz():
    # 낙상 모델 적재 가능 여부로 readiness 표시. (P1-1: 과거 존재하지 않는 SP._fall_model
    # 참조로 500 → _model_for("watch") 의 적재 결과를 사용하도록 교정.)
    return jsonify({"ok": True, "service": "widu",
                    "fall_model": SP._model_for("watch").trained})


@app.post("/users/<uid>/hr")
def hr(uid):
    d = request.get_json(force=True)
    _require(d, "bpm")
    acc = _enum(Accuracy, d.get("accuracy", "UNKNOWN"), "accuracy")
    a = SP.ingest_hr(uid, HRSample(_ts(d), _num(d, "bpm"), acc))
    return jsonify(a.to_dict())


@app.post("/users/<uid>/imu")
def imu(uid):
    d = request.get_json(force=True)
    _require(d, "ax", "ay", "az")
    # P1-3: source(watch/phone)를 수용해 위치별 모델(손목/허리) 라우팅을 살린다.
    # 미전달 시 기존 동작 보존(source="watch"). (IMUSample.accuracy 는 파이프라인 미소비 →
    # 의도적으로 받지 않음 — HR 의 Accuracy enum 과 혼동 방지.)
    a = SP.ingest_imu(uid, IMUSample(
        _ts(d), _num(d, "ax"), _num(d, "ay"), _num(d, "az"),
        _num(d, "gx", 0), _num(d, "gy", 0), _num(d, "gz", 0),
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
                             confidence=_num(d, "confidence", 0.95))
    return jsonify(a.to_dict())


@app.post("/users/<uid>/location")
def location(uid):
    d = request.get_json(force=True)
    _require(d, "lat", "lon")
    a = SP.ingest_location(uid, LocSample(_ts(d), _num(d, "lat"), _num(d, "lon"),
                                          d.get("speed")))
    return jsonify(a.to_dict() if a else {"status": "ok"})


@app.post("/users/<uid>/record")
def record(uid):
    d = request.get_json(force=True)
    _require(d, "kind", "value")
    kind = _enum(RecordKind, d["kind"], "kind")
    a = SP.ingest_record(uid, RecordSample(_ts(d), kind, _num(d, "value")))
    return jsonify(a.to_dict() if a else {"status": "ok"})


@app.post("/users/<uid>/safezones")
def safezones(uid):
    d = request.get_json(force=True)
    _require(d, "zones")
    zones = d["zones"]
    if not isinstance(zones, list):
        raise BadRequest("zones must be a list of [lat, lon, radius]")
    try:
        pairs = [tuple(z) for z in zones]
    except TypeError:
        raise BadRequest("each zone must be a list like [lat, lon, radius]")
    SP.set_safe_zones(uid, pairs)
    return jsonify({"status": "ok", "count": len(pairs)})


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
    _require(d, "is_fall")
    sid = SP.confirm_incident(uid, bool(d["is_fall"]), by=d.get("by", "guardian"))
    return jsonify({"status": "ok", "sample_id": sid, "labeled": sid is not None})


@app.get("/collector/stats")
def collector_stats():
    return jsonify(SP.collector.stats())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
