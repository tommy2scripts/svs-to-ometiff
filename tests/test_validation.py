"""Validation and metadata edge-case tests."""

from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pytest
import tifffile

from svs_to_ometiff.pyramid import build_pyramid
from svs_to_ometiff.tile_reader import _decode_tile_payload, parse_mpp_from_description
from svs_to_ometiff.writer import build_ome_xml, write_pyramidal_ometiff


def test_build_pyramid_rejects_non_rgb_input() -> None:
    image = np.zeros((8, 8), dtype=np.uint8)

    with pytest.raises(ValueError, match=r"\(H, W, 3\)"):
        build_pyramid(image, verbose=False)


def test_build_pyramid_allows_single_level_small_image() -> None:
    image = np.zeros((1, 1, 3), dtype=np.uint8)

    pyramid = build_pyramid(image, num_levels=1, verbose=False)

    assert pyramid == [image]


def test_build_pyramid_rejects_too_many_levels() -> None:
    image = np.zeros((2, 2, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="Cannot build level 2"):
        build_pyramid(image, num_levels=3, verbose=False)


def test_build_pyramid_uses_progress_logger() -> None:
    messages: list[str] = []
    image = np.zeros((4, 4, 3), dtype=np.uint8)

    build_pyramid(
        image,
        num_levels=2,
        verbose=True,
        progress_logger=messages.append,
    )

    assert any("Level 1" in message for message in messages)
    assert any("Pyramid built" in message for message in messages)


def test_build_ome_xml_escapes_image_name() -> None:
    xml = build_ome_xml(10, 12, 0.5, image_name='A&B "slide" <test> >')
    root = ElementTree.fromstring(xml)
    image = root.find("{http://www.openmicroscopy.org/Schemas/OME/2016-06}Image")

    assert image is not None
    assert image.attrib["Name"] == 'A&B "slide" <test> >'


def test_write_pyramidal_ometiff_keeps_escaped_name_parseable_for_tifffile(
    tmp_path: Path,
) -> None:
    output = tmp_path / "escaped-name.ome.tiff"
    image_name = 'A&B "slide" <test> >'
    pyramid = [np.zeros((16, 16, 3), dtype=np.uint8)]

    write_pyramidal_ometiff(
        str(output),
        pyramid,
        0.5,
        tile_size=16,
        compression=None,
        image_name=image_name,
        verbose=False,
    )

    with tifffile.TiffFile(output) as tif:
        ome_xml = tif.ome_metadata

    assert ome_xml is not None
    root = ElementTree.fromstring(ome_xml)
    image = root.find("{http://www.openmicroscopy.org/Schemas/OME/2016-06}Image")
    assert image is not None
    assert image.attrib["Name"] == image_name


def test_build_ome_xml_rejects_invalid_mpp() -> None:
    with pytest.raises(ValueError, match="mpp must be positive"):
        build_ome_xml(10, 12, 0)


def test_write_pyramidal_ometiff_rejects_bad_sublevel(tmp_path: Path) -> None:
    output = tmp_path / "bad.ome.tiff"
    pyramid = [
        np.zeros((16, 16, 3), dtype=np.uint8),
        np.zeros((8, 8), dtype=np.uint8),
    ]

    with pytest.raises(ValueError, match="Pyramid level 1"):
        write_pyramidal_ometiff(str(output), pyramid, 0.5, verbose=False)


def test_write_pyramidal_ometiff_rejects_invalid_tile_size(tmp_path: Path) -> None:
    output = tmp_path / "bad.ome.tiff"
    pyramid = [np.zeros((16, 16, 3), dtype=np.uint8)]

    with pytest.raises(ValueError, match="divisible by 16"):
        write_pyramidal_ometiff(str(output), pyramid, 0.5, tile_size=10, verbose=False)


def test_parse_mpp_requires_exact_key() -> None:
    with pytest.raises(ValueError, match="MPP not found"):
        parse_mpp_from_description("Aperio|MPP2 = 0.25")

    assert parse_mpp_from_description("Aperio| mpp = 0.25") == 0.25


def test_parse_mpp_rejects_non_positive_value() -> None:
    with pytest.raises(ValueError, match="MPP must be positive"):
        parse_mpp_from_description("Aperio|MPP = 0")


def test_decode_tile_payload_accepts_cropped_edge_payload() -> None:
    raw = bytes([128, 128, 128, 128]) * 2

    tile = _decode_tile_payload(
        raw,
        full_tile_width=4,
        full_tile_height=4,
        visible_width=4,
        visible_height=1,
    )

    assert tile.shape == (1, 4, 3)
    np.testing.assert_array_equal(tile, 128)
