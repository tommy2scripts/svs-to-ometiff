"""Tests for domain models — ConversionJob and SlideMetadata."""

import pickle

from svs_to_ometiff.config import ConvertConfig
from svs_to_ometiff_gui.models import ConversionJob, SlideMetadata


class TestConversionJob:
    """ConversionJob dataclass and converter kwargs generation."""

    def test_defaults(self):
        job = ConversionJob(input_path="/path/to/slide.svs")
        assert job.tile_size == 1024
        assert job.compression == "zlib"
        assert job.num_levels == 6
        assert job.downsample_factor == 2
        assert job.edge_mode == "crop"

    def test_to_converter_kwargs(self):
        job = ConversionJob(
            input_path="/in.svs",
            output_path="/out.ome.tiff",
            tile_size=256,
            compression="zlib",
        )
        kw = job.to_converter_kwargs()
        assert kw["config_or_input_svs"] == "/in.svs"
        assert kw["output_ometiff"] == "/out.ome.tiff"
        assert kw["tile_size"] == 256
        assert kw["compression"] == "zlib"

    def test_none_compression(self):
        job = ConversionJob(input_path="/in.svs", compression="none")
        kw = job.to_converter_kwargs()
        assert kw["compression"] is None

    def test_empty_output_becomes_none(self):
        job = ConversionJob(input_path="/in.svs", output_path="")
        kw = job.to_converter_kwargs()
        assert kw["output_ometiff"] is None

    def test_conversion_config_is_authoritative_shape(self):
        job = ConversionJob(
            input_path="/in.svs",
            output_path="/out.ome.tiff",
            tile_size=512,
            compression="none",
            compressionargs={"level": 80},
        )

        config = job.to_convert_config()

        assert isinstance(config, ConvertConfig)
        assert config.input_svs == "/in.svs"
        assert config.output_ometiff == "/out.ome.tiff"
        assert config.tile_size == 512
        assert config.compression is None
        assert config.compressionargs == {"level": 80}

    def test_from_convert_config_preserves_gui_job_fields(self):
        config = ConvertConfig(
            input_svs="/in.svs",
            output_ometiff="/out.ome.tiff",
            tile_size=512,
            compression="jpeg",
            compressionargs={"level": 85},
        )

        job = ConversionJob.from_convert_config(config, request_id="abc123")

        assert job.input_path == "/in.svs"
        assert job.output_path == "/out.ome.tiff"
        assert job.tile_size == 512
        assert job.compression == "jpeg"
        assert job.compressionargs == {"level": 85}
        assert job.request_id == "abc123"

    def test_converter_kwargs_are_pickle_safe(self):
        job = ConversionJob(
            input_path="/in.svs",
            output_path="/out.ome.tiff",
            compressionargs={"level": 85},
        )

        kwargs = job.to_converter_kwargs()

        assert pickle.loads(pickle.dumps(kwargs)) == kwargs


class TestSlideMetadata:
    """SlideMetadata from_dict construction."""

    def test_from_dict_full(self):
        data = {
            "width": 100000,
            "height": 50000,
            "mpp": 0.25,
            "magnification": 40.0,
            "compression": "JPEG",
            "src_tile_width": 256,
            "src_tile_height": 256,
            "tile_count": 1500,
            "convertible": True,
        }
        md = SlideMetadata.from_dict(data)
        assert md.width == 100000
        assert md.magnification == 40.0
        assert md.convertible is True

    def test_from_dict_missing_keys(self):
        md = SlideMetadata.from_dict({})
        assert md.width == 0
        assert md.mpp is None
        assert md.convertible is False
