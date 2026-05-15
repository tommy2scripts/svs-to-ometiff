"""
Tests that GUI request parameters normalize correctly to ConvertConfig.

The GUI sends string-typed values in its JSON payload; the conversion
endpoint must coerce them to the types ConvertConfig expects and normalize
``"none"`` compression to ``None``.
"""

from svs_to_ometiff.config import ConvertConfig


def _simulate_gui_params(
    input_path: str = "/fake/input.svs",
    output_path: str = "/fake/output.ome.tiff",
    tile_size: str = "1024",
    compression: str = "zlib",
    num_levels: str = "6",
    downsample_factor: str = "2",
    edge_mode: str = "crop",
) -> ConvertConfig:
    """Simulate the normalization the GUI endpoint applies before conversion."""
    compression_normalized = None if compression == "none" else compression
    return ConvertConfig(
        input_svs=input_path,
        output_ometiff=output_path,
        tile_size=int(tile_size),
        compression=compression_normalized,
        num_levels=int(num_levels),
        downsample_factor=int(downsample_factor),
        edge_mode=edge_mode,
        verbose=True,
    )


def test_gui_params_default_compression_is_zlib() -> None:
    """GUI sends compression='zlib' by default."""
    config = _simulate_gui_params()
    assert config.compression == "zlib"


def test_gui_params_explicit_lzw_compression() -> None:
    """GUI sends compression='lzw' → ConvertConfig stores 'lzw'."""
    config = _simulate_gui_params(compression="lzw")
    assert config.compression == "lzw"


def test_gui_params_strings_are_coerced_to_ints() -> None:
    """GUI sends string tile_size='512' → ConvertConfig gets int 512."""
    config = _simulate_gui_params(tile_size="1024", num_levels="5", downsample_factor="4")
    assert config.tile_size == 1024
    assert config.num_levels == 5
    assert config.downsample_factor == 4


def test_gui_params_edge_mode_passthrough() -> None:
    """GUI edge_mode passes through as-is."""
    config = _simulate_gui_params(edge_mode="pad")
    assert config.edge_mode == "pad"


def test_gui_params_edge_mode_default_crop() -> None:
    """GUI edge_mode defaults to crop."""
    config = _simulate_gui_params(edge_mode="crop")
    assert config.edge_mode == "crop"


def test_gui_params_default_tile_size_is_1024() -> None:
    """GUI default tile_size matches the public profile."""
    config = _simulate_gui_params()
    assert config.tile_size == 1024


def test_gui_params_default_num_levels_is_6() -> None:
    """GUI default num_levels matches the public profile."""
    config = _simulate_gui_params()
    assert config.num_levels == 6


def test_gui_params_none_compression_stored_as_none() -> None:
    """Compression='none' string is normalized to Python None before ConvertConfig."""
    config = _simulate_gui_params(compression="none")
    assert config.compression is None


def test_gui_params_zlib_compression_stored_as_string() -> None:
    """Compression='zlib' passes through as the string 'zlib'."""
    config = _simulate_gui_params(compression="zlib")
    assert config.compression == "zlib"


def test_gui_params_deflate_compression_stored_as_string() -> None:
    """Compression='deflate' passes through as the string 'deflate'."""
    config = _simulate_gui_params(compression="deflate")
    assert config.compression == "deflate"
