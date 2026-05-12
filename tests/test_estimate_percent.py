"""Tests for _estimate_percent — progress message parsing logic."""

import pytest

from svs_to_ometiff_gui.serve import _estimate_percent


class TestTileRowParsing:
    """The 'Tile row X of Y' pattern maps to 10-60%."""

    def test_first_tile_row(self):
        assert _estimate_percent("Tile row 1 of 20") == pytest.approx(12.5)

    def test_middle_tile_row(self):
        assert _estimate_percent("Tile row 10 of 20") == pytest.approx(35.0)

    def test_last_tile_row(self):
        assert _estimate_percent("Tile row 20 of 20") == pytest.approx(60.0)

    def test_tile_row_case_insensitive(self):
        result = _estimate_percent("tile row 5 of 10")
        assert result is not None
        assert 10.0 <= result <= 60.0

    def test_tile_row_zero_total(self):
        """Zero total should not divide by zero — returns None."""
        assert _estimate_percent("Tile row 0 of 0") is None


class TestKeywordPhases:
    """Keyword-based phase detection."""

    def test_reading_metadata(self):
        assert _estimate_percent("Reading metadata from file") == 5.0

    def test_opening_file(self):
        assert _estimate_percent("Opening SVS file") == 5.0

    def test_building_pyramid(self):
        assert _estimate_percent("Building pyramid levels") == 62.0

    def test_pyramid_built(self):
        assert _estimate_percent("Pyramid built successfully") == 82.0

    def test_writing_ome_tiff(self):
        assert _estimate_percent("Writing OME-TIFF output") == 86.0

    def test_level_memmap(self):
        assert _estimate_percent("Level 3 memmap allocated") == 70.0

    def test_level_indented(self):
        assert _estimate_percent("  level 2: 1024x768") == 92.0

    def test_done_message(self):
        assert _estimate_percent("Done in 45.2s") == 100.0


class TestUnknownMessages:
    """Messages we don't recognize should return None."""

    def test_random_message(self):
        assert _estimate_percent("Something unexpected happened") is None

    def test_empty_string(self):
        assert _estimate_percent("") is None

    def test_whitespace_only(self):
        assert _estimate_percent("   ") is None
