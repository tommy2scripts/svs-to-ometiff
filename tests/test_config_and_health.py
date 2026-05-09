"""Tests for config, logging, and health check (Phases 3 & 5)."""

import json
import os

import pytest


class TestConfig:
    """Config loads from environment with defaults."""

    def test_default_values(self):
        from svs_to_ometiff_gui.config import Config
        cfg = Config()
        assert cfg.HOST == os.environ.get("SVS_GUI_HOST", "127.0.0.1")
        assert cfg.PORT == int(os.environ.get("SVS_GUI_PORT", "8765"))
        assert cfg.DEFAULT_TILE_SIZE == 1024

    def test_default_port(self):
        from svs_to_ometiff_gui.config import Config
        cfg = Config()
        # Default port when SVS_GUI_PORT is not set is 8765
        assert isinstance(cfg.PORT, int)
        assert cfg.PORT > 0


class TestHealthCheck:
    """GET /health returns status information."""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert data["version"] == "0.2.0"
        assert "active_jobs" in data

    def test_health_shows_no_active_jobs(self, client):
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert data["active_jobs"] == 0
