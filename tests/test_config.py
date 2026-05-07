"""ConvertConfig validation tests."""

import pytest

from svs_to_ometiff.config import ConvertConfig


def _make_config(**kwargs) -> ConvertConfig:
    values = {"input_svs": "input.svs", "output_ometiff": "output.ome.tiff"}
    values.update(kwargs)
    return ConvertConfig(**values)


@pytest.mark.parametrize("tile_size", [0, -16])
def test_convert_config_rejects_non_positive_tile_size(tile_size: int) -> None:
    with pytest.raises(ValueError, match="tile_size must be positive"):
        _make_config(tile_size=tile_size)


@pytest.mark.parametrize("tile_size", [1, 15, 17, 510])
def test_convert_config_rejects_tile_size_not_divisible_by_16(tile_size: int) -> None:
    with pytest.raises(ValueError, match="tile_size must be divisible by 16"):
        _make_config(tile_size=tile_size)


@pytest.mark.parametrize("num_levels", [0, -1])
def test_convert_config_rejects_num_levels_below_one(num_levels: int) -> None:
    with pytest.raises(ValueError, match="num_levels must be at least 1"):
        _make_config(num_levels=num_levels)


@pytest.mark.parametrize("downsample_factor", [0, 1, -2])
def test_convert_config_rejects_downsample_factor_below_two(
    downsample_factor: int,
) -> None:
    with pytest.raises(ValueError, match="downsample_factor must be at least 2"):
        _make_config(downsample_factor=downsample_factor)


@pytest.mark.parametrize("compression", ["jpeg", "none", "LZW", ""])
def test_convert_config_rejects_unsupported_compression(compression: str) -> None:
    with pytest.raises(ValueError, match="compression must be one of"):
        _make_config(compression=compression)


@pytest.mark.parametrize("compression", [None, "lzw", "zlib", "deflate"])
def test_convert_config_accepts_supported_compression_values(
    compression: str | None,
) -> None:
    config = _make_config(compression=compression)

    assert config.compression == compression
