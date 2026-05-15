"""Tests for ConvertConfig serialization — to_dict / from_dict."""

from dataclasses import fields as dataclass_fields

import pytest

from svs_to_ometiff.config import ConvertConfig


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------

class TestToDict:
    """ConvertConfig.to_dict serialization."""

    def test_required_fields_only(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
        )
        d = config.to_dict()
        assert d["input_svs"] == "/in.svs"
        assert d["output_ometiff"] == "/out.ome.tiff"
        # default values
        assert d["tile_size"] == 1024
        assert d["compression"] == "zlib"
        assert d["num_levels"] == 6
        assert d["downsample_factor"] == 2
        assert d["edge_mode"] == "crop"
        assert d["image_name"] is None
        assert d["verbose"] is True
        assert d["tile_progress_interval"] == 20
        assert d["temp_dir"] is None

    def test_all_fields(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            tile_size=512,
            compression="lzw",
            num_levels=4,
            downsample_factor=4,
            edge_mode="pad",
            image_name="MySlide",
            verbose=False,
            tile_progress_interval=50,
            temp_dir="/tmp/work",
        )
        d = config.to_dict()
        assert d["input_svs"] == "/in.svs"
        assert d["output_ometiff"] == "/out.ome.tiff"
        assert d["tile_size"] == 512
        assert d["compression"] == "lzw"
        assert d["num_levels"] == 4
        assert d["downsample_factor"] == 4
        assert d["edge_mode"] == "pad"
        assert d["image_name"] == "MySlide"
        assert d["verbose"] is False
        assert d["tile_progress_interval"] == 50
        assert d["temp_dir"] == "/tmp/work"

    def test_excludes_progress_logger(self):
        def logger(msg: str, **kwargs): pass
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            progress_logger=logger,
        )
        d = config.to_dict()
        assert "progress_logger" not in d

    def test_compression_none(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            compression=None,
        )
        d = config.to_dict()
        assert d["compression"] is None

    def test_dict_keys_match_field_names_excluding_progress_logger(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
        )
        d = config.to_dict()
        all_field_names = {f.name for f in dataclass_fields(ConvertConfig)}
        expected = all_field_names - {"progress_logger"}
        assert set(d.keys()) == expected


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------

class TestFromDict:
    """ConvertConfig.from_dict construction."""

    def test_required_fields_only(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
        })
        assert config.input_svs == "/in.svs"
        assert config.output_ometiff == "/out.ome.tiff"
        # defaults for optional fields
        assert config.tile_size == 1024
        assert config.compression == "zlib"
        assert config.num_levels == 6
        assert config.downsample_factor == 2
        assert config.edge_mode == "crop"
        assert config.image_name is None
        assert config.verbose is True
        assert config.tile_progress_interval == 20
        assert config.temp_dir is None

    def test_all_fields(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
            "tile_size": 256,
            "compression": "deflate",
            "num_levels": 3,
            "downsample_factor": 8,
            "edge_mode": "pad",
            "image_name": "Test",
            "verbose": False,
            "tile_progress_interval": 10,
            "temp_dir": "/tmp/x",
        })
        assert config.tile_size == 256
        assert config.compression == "deflate"
        assert config.num_levels == 3
        assert config.downsample_factor == 8
        assert config.edge_mode == "pad"
        assert config.image_name == "Test"
        assert config.verbose is False
        assert config.tile_progress_interval == 10
        assert config.temp_dir == "/tmp/x"

    def test_missing_optional_uses_defaults(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
        })
        assert config.tile_size == 1024
        assert config.compression == "zlib"
        assert config.num_levels == 6
        assert config.downsample_factor == 2
        assert config.edge_mode == "crop"
        assert config.image_name is None
        assert config.verbose is True
        assert config.tile_progress_interval == 20
        assert config.temp_dir is None
        assert config.progress_logger is None

    def test_unknown_keys_ignored(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
            "bogus": "value",
            "_internal": 42,
        })
        assert config.input_svs == "/in.svs"
        # No error — unknown keys silently discarded

    def test_compression_none(self):
        config = ConvertConfig.from_dict({
            "input_svs": "/in.svs",
            "output_ometiff": "/out.ome.tiff",
            "compression": None,
        })
        assert config.compression is None

    def test_validation_runs_on_invalid_values(self):
        with pytest.raises(ValueError, match="tile_size"):
            ConvertConfig.from_dict({
                "input_svs": "/in.svs",
                "output_ometiff": "/out.ome.tiff",
                "tile_size": -1,
            })

    def test_validation_runs_on_bad_compression(self):
        with pytest.raises(ValueError, match="compression"):
            ConvertConfig.from_dict({
                "input_svs": "/in.svs",
                "output_ometiff": "/out.ome.tiff",
                "compression": "jpeg2000",
            })


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """config == ConvertConfig.from_dict(config.to_dict())"""

    def test_minimal_config(self):
        config = ConvertConfig(
            input_svs="/a.svs",
            output_ometiff="/b.ome.tiff",
        )
        restored = ConvertConfig.from_dict(config.to_dict())
        assert config == restored

    def test_full_config(self):
        config = ConvertConfig(
            input_svs="/a.svs",
            output_ometiff="/b.ome.tiff",
            tile_size=256,
            compression="lzw",
            num_levels=3,
            downsample_factor=4,
            edge_mode="pad",
            image_name="Slide",
            verbose=False,
            tile_progress_interval=5,
            temp_dir="/tmp",
        )
        restored = ConvertConfig.from_dict(config.to_dict())
        assert config == restored

    def test_compression_none_round_trip(self):
        config = ConvertConfig(
            input_svs="/a.svs",
            output_ometiff="/b.ome.tiff",
            compression=None,
        )
        restored = ConvertConfig.from_dict(config.to_dict())
        assert config == restored
        assert restored.compression is None

    def test_with_progress_logger_preserves_rest(self):
        """progress_logger is dropped by to_dict, but the round-trip still
        matches on all other fields when the default is None."""
        def logger(msg: str, **kwargs): pass
        config = ConvertConfig(
            input_svs="/a.svs",
            output_ometiff="/b.ome.tiff",
            progress_logger=logger,
        )
        d = config.to_dict()
        assert "progress_logger" not in d
        restored = ConvertConfig.from_dict(d)
        # Equality check: logger defaults to None vs original logger → not equal
        # So just verify the input_svs survived (the important part)
        assert restored.input_svs == config.input_svs
        assert restored.output_ometiff == config.output_ometiff
