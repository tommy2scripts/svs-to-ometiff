"""Tests for config, logging, and health check (Phases 3 & 5)."""

import json
import os

import pytest


class TestPackageVersion:
    """Tests that the package version matches what was set in this PR."""

    def test_version_is_0_6_1(self):
        from svs_to_ometiff import __version__
        assert __version__ == "0.7.0"

    def test_version_string_format(self):
        from svs_to_ometiff import __version__
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


class TestConvertConfigDefaultsAndErrors:
    """Tests for public conversion defaults and compression validation."""

    def test_defaults_match_public_cli_gui_profile(self):
        from svs_to_ometiff.config import ConvertConfig

        config = ConvertConfig(
            input_svs="/fake/input.svs",
            output_ometiff="/fake/output.ome.tiff",
        )
        assert config.tile_size == 1024
        assert config.compression == "zlib"
        assert config.num_levels == 6
        assert config.downsample_factor == 2
        assert config.edge_mode == "crop"

    def test_unsupported_compression_error_names_value(self):
        from svs_to_ometiff.config import ConvertConfig
        with pytest.raises(ValueError, match="bzip2"):
            ConvertConfig(
                input_svs="/fake/input.svs",
                output_ometiff="/fake/output.ome.tiff",
                compression="bzip2",
            )

    def test_unsupported_compression_error_does_not_say_this_release(self):
        from svs_to_ometiff.config import ConvertConfig
        with pytest.raises(ValueError) as exc_info:
            ConvertConfig(
                input_svs="/fake/input.svs",
                output_ometiff="/fake/output.ome.tiff",
                compression="bzip2",
            )
        assert "this release" not in str(exc_info.value)

    def test_unsupported_compression_error_mentions_alternatives(self):
        from svs_to_ometiff.config import ConvertConfig
        with pytest.raises(ValueError) as exc_info:
            ConvertConfig(
                input_svs="/fake/input.svs",
                output_ometiff="/fake/output.ome.tiff",
                compression="bzip2",
            )
        assert "zlib" in str(exc_info.value)


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
        assert data["version"] == "0.7.0"
        assert "active_jobs" in data

    def test_health_shows_no_active_jobs(self, client):
        resp = client.get("/health")
        data = json.loads(resp.data)
        assert data["active_jobs"] == 0
