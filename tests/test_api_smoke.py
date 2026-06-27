"""Flask 서빙 API 스모크 테스트 — 라우트 존재·기본 응답 계약만 보수적으로 확인.

서버를 실제로 띄우지 않고 Flask test_client 로 in-process 호출.
값 의미가 아니라 '계약(상태코드·필수 키)'을 검증한다. 상세 스키마는
docs/API_CONTRACTS.md 참조.
"""
from __future__ import annotations

import pytest

from serving.api import app, SP


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_healthz(client):
    # P1-1 수정 후: 과거 AttributeError(500) → 정상 200. fall_model 적재 여부 bool 반환.
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["service"] == "widu"
    assert "fall_model" in body
    assert isinstance(body["fall_model"], bool)


def test_post_hr_returns_assessment(client):
    r = client.post("/users/u1/hr", json={"ts": 1000.0, "bpm": 72.0,
                                          "accuracy": "HIGH"})
    assert r.status_code == 200
    body = r.get_json()
    # Assessment.to_dict() 계약
    for key in ("ts", "level", "reason", "escalation", "context", "detections"):
        assert key in body
    assert isinstance(body["detections"], list)


def test_post_imu_ok(client):
    r = client.post("/users/u1/imu", json={"ts": 1000.0, "ax": 0.0,
                                           "ay": 0.0, "az": 1.0})
    assert r.status_code == 200
    # 탐지 없으면 {"status": "ok"}, 있으면 Assessment dict — 둘 다 200
    assert r.get_json() is not None


def test_post_location_ok(client):
    r = client.post("/users/u1/location", json={"ts": 1000.0, "lat": 37.5,
                                                "lon": 127.0})
    assert r.status_code == 200


def test_post_record_ok(client):
    r = client.post("/users/u1/record", json={"ts": 1000.0, "kind": "RESTING_HR",
                                              "value": 70.0})
    assert r.status_code == 200


def test_set_safezones(client):
    r = client.post("/users/u1/safezones",
                    json={"zones": [[37.5, 127.0, 150.0]]})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert body["count"] == 1


def test_get_status(client):
    r = client.get("/users/u1/status")
    assert r.status_code == 200
    assert "level" in r.get_json()


def test_respond_ok(client):
    r = client.post("/users/u1/respond_ok", json={"ts": 1000.0})
    assert r.status_code == 200
    assert "level" in r.get_json()


def test_confirm_incident(client):
    # 대기 이벤트가 없으면 labeled=False, sample_id=None 이지만 200 계약은 유지
    r = client.post("/users/u1/confirm_incident",
                    json={"is_fall": True, "by": "guardian"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["status"] == "ok"
    assert "labeled" in body


def test_collector_stats(client):
    r = client.get("/collector/stats")
    assert r.status_code == 200
    assert "enabled" in r.get_json()


# --------------------------------------------------------------------------- #
# P1-2 입력 검증 — 잘못된 요청은 500 이 아니라 400 (회귀 가드)
# --------------------------------------------------------------------------- #
def test_hr_missing_bpm_returns_400(client):
    r = client.post("/users/uerr/hr", json={"ts": 1000.0, "accuracy": "HIGH"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "missing_field"


def test_hr_bad_accuracy_enum_returns_400(client):
    r = client.post("/users/uerr/hr", json={"ts": 1000.0, "bpm": 72.0,
                                            "accuracy": "NONSENSE"})
    assert r.status_code == 400


def test_record_bad_kind_enum_returns_400(client):
    r = client.post("/users/uerr/record", json={"ts": 1000.0, "kind": "BOGUS",
                                                "value": 1.0})
    assert r.status_code == 400


def test_hr_non_numeric_bpm_returns_400(client):
    r = client.post("/users/uerr/hr", json={"ts": 1000.0, "bpm": "abc",
                                            "accuracy": "HIGH"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# P1-3 IMU source 수용 — /imu 가 source 를 실제로 파이프라인에 전달하는지(회귀 가드)
# --------------------------------------------------------------------------- #
def test_imu_source_phone_is_forwarded(client):
    uid = "usrc_phone"
    r = client.post(f"/users/{uid}/imu", json={"ts": 1000.0, "ax": 0.0, "ay": 0.0,
                                               "az": 1.0, "source": "phone"})
    assert r.status_code == 200
    # source 가 전달됐다면 phone 위치 전용 낙상 탐지기가 생성돼 있어야 한다.
    assert "phone" in SP._users[uid].l2


def test_imu_default_source_is_watch(client):
    uid = "usrc_default"
    r = client.post(f"/users/{uid}/imu", json={"ts": 1000.0, "ax": 0.0, "ay": 0.0,
                                               "az": 1.0})
    assert r.status_code == 200
    assert "watch" in SP._users[uid].l2


# --------------------------------------------------------------------------- #
# P1-4 네이티브 낙상 라우트 — ingest_fall_event 위임(회귀 가드)
# --------------------------------------------------------------------------- #
def test_native_fall_route_returns_emergency(client):
    r = client.post("/users/unative/native_fall",
                    json={"ts": 1000.0, "source": "watch", "confidence": 0.95})
    assert r.status_code == 200
    body = r.get_json()
    assert body["level"] == "EMERGENCY"
    for key in ("ts", "level", "reason", "escalation", "context", "detections"):
        assert key in body


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
