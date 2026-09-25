"""Tests de `GET /api/v1/health` (RF-09, RNF-02)."""

import time

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_RF_09_health_responde_ok_y_version():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]


def test_RNF_02_health_responde_bajo_300ms():
    inicio = time.perf_counter()
    response = client.get("/api/v1/health")
    duracion_ms = (time.perf_counter() - inicio) * 1000

    assert response.status_code == 200
    assert duracion_ms < 300
