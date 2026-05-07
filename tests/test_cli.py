"""CLI option and safe-default tests."""

from click.testing import CliRunner

from svs_to_ometiff.config import ConvertConfig
from svs_to_ometiff.converter import _coerce_convert_config
from svs_to_ometiff.cli import main


def test_convert_config_uses_safe_production_defaults() -> None:
    config = ConvertConfig(input_svs="input.svs", output_ometiff="output.ome.tiff")

    assert config.tile_size == 512
    assert config.compression is None
    assert config.num_levels == 3
    assert config.downsample_factor == 2


def test_legacy_convert_arguments_use_safe_production_defaults() -> None:
    config = _coerce_convert_config("input.svs", "output.ome.tiff", {})

    assert config.tile_size == 512
    assert config.compression is None
    assert config.num_levels == 3
    assert config.downsample_factor == 2


def test_cli_help_shows_safe_production_defaults() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--compression [lzw|zlib|deflate|none]" in result.output
    assert "[default: none]" in result.output
    assert "--num-levels INTEGER" in result.output
    assert "[default: 3]" in result.output
    assert "--tile-size INTEGER" in result.output
    assert "[default: 512]" in result.output
    assert "--downsample-factor INTEGER" in result.output
    assert "[default: 2]" in result.output
