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
        assert data["version"] == "0.5.1"
        assert "active_jobs" in data

    def test_health_shows_no_active_jobs(self, client):
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert data["active_jobs"] == 0


class TestConvertConfigVersionMessage:
    """ConvertConfig error messages reference the current version string."""

    def test_jpeg2000_error_contains_version_051(self):
        """jpeg2000 compression error must mention '0.5.1' (not 'this release')."""
        from svs_to_ometiff.config import ConvertConfig
        with pytest.raises(ValueError, match="0.5.1"):
            ConvertConfig(
                input_svs="/fake/input.svs",
                output_ometiff="/fake/output.ome.tiff",
                tile_size=512,
                compression="jpeg2000",
            )

    def test_jpeg2000_error_does_not_say_this_release(self):
        """The old 'this release' wording must no longer appear in the error."""
        from svs_to_ometiff.config import ConvertConfig
        with pytest.raises(ValueError) as exc_info:
            ConvertConfig(
                input_svs="/fake/input.svs",
                output_ometiff="/fake/output.ome.tiff",
                tile_size=512,
                compression="jpeg2000",
            )
        assert "this release" not in str(exc_info.value)


class TestPackageVersion:
    """Package __version__ reflects the current release."""

    def test_version_is_051(self):
        from svs_to_ometiff import __version__
        assert __version__ == "0.5.1"
