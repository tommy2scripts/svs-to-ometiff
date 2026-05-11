"""
Tests for the YUYV → RGB decoder.

Validates colour conversion accuracy and edge case handling.
"""

import numpy as np
import pytest

from svs_to_ometiff.yuyv_decoder import yuyv_to_rgb


def _make_yuyv(y0: int, u: int, y1: int, v: int) -> bytes:
    """Make a 4-byte YUYV group for 2 pixels."""
    return bytes([y0 & 0xFF, u & 0xFF, y1 & 0xFF, v & 0xFF])


class TestYUYVDecoder:
    """Test the YUYV to RGB decoder."""

    def test_grayscale_mid(self):
        """Mid-gray YUYV should produce equal RGB channels."""
        # Y=128, Cb=128, Cr=128 -> R=128, G=128, B=128
        raw = _make_yuyv(128, 128, 128, 128) * (2 * 2 // 2)  # 2x2 tile = 2 pairs
        rgb = yuyv_to_rgb(raw, tile_width=2, tile_height=2)
        assert rgb.shape == (2, 2, 3)
        assert rgb.dtype == np.uint8
        np.testing.assert_array_equal(rgb[:, :, 0], 128)
        np.testing.assert_array_equal(rgb[:, :, 1], 128)
        np.testing.assert_array_equal(rgb[:, :, 2], 128)

    def test_black_yuv(self):
        """Full-range black YUYV gives near-black RGB."""
        # Full-range Y=0, Cb=128, Cr=128 -> R=0, G=0, B=0
        raw = _make_yuyv(0, 128, 0, 128) * (4 * 4 // 2)
        rgb = yuyv_to_rgb(raw, tile_width=4, tile_height=4)
        assert np.all(rgb <= 1)  # Clipped to 0

    def test_white_yuv(self):
        """White YUYV gives white RGB."""
        raw = _make_yuyv(255, 128, 255, 128) * (4 * 4 // 2)
        rgb = yuyv_to_rgb(raw, tile_width=4, tile_height=4)
        assert np.all(rgb >= 254)

    def test_red_tint(self):
        """High Cr gives red tint."""
        # Y=200, Cb=128, Cr=200
        # R = 200 + 1.402 * (200-128) = 200 + 100.944 = 300.944 → clip to 255
        # G = 200 - 0 - 0.714136*72 = 200 - 51.4 = 148.6
        # B = 200 + 0 = 200
        raw = _make_yuyv(200, 128, 200, 200) * (2 * 2 // 2)
        rgb = yuyv_to_rgb(raw, tile_width=2, tile_height=2)
        # R should be clipped to 255
        r = int(rgb[0, 0, 0])
        g = int(rgb[0, 0, 1])
        b = int(rgb[0, 0, 2])
        assert r == 255
        assert 145 < g < 155  # ~148
        assert 195 < b < 205  # ~200

    def test_blue_tint(self):
        """High Cb gives blue tint."""
        # Y=200, Cb=200, Cr=128
        # R = 200 + 0 = 200
        # G = 200 - 0.344136*72 - 0 = 200 - 24.8 = 175.2
        # B = 200 + 1.772*72 = 200 + 127.6 = 327.6 → clip to 255
        raw = _make_yuyv(200, 200, 200, 128) * (2 * 2 // 2)
        rgb = yuyv_to_rgb(raw, tile_width=2, tile_height=2)
        r = int(rgb[0, 0, 0])
        g = int(rgb[0, 0, 1])
        b = int(rgb[0, 0, 2])
        assert 195 < r < 205  # ~200
        assert 170 < g < 180  # ~175
        assert b == 255

    def test_tile_size_256x256(self):
        """Full 256x256 tile (standard SVS tile size)."""
        raw = _make_yuyv(180, 128, 180, 128) * (256 * 256 // 2)
        rgb = yuyv_to_rgb(raw, tile_width=256, tile_height=256)
        assert rgb.shape == (256, 256, 3)

    def test_wrong_byte_count_raises(self):
        """Wrong number of bytes should raise ValueError."""
        raw = b"\x00" * 100  # Not 131072
        with pytest.raises(ValueError, match="Expected"):
            yuyv_to_rgb(raw, tile_width=256, tile_height=256)

    def test_odd_tile_width_raises(self):
        """YUYV 4:2:2 requires an even tile width."""
        raw = b"\x00" * 30
        with pytest.raises(ValueError, match="even tile_width"):
            yuyv_to_rgb(raw, tile_width=3, tile_height=5)

    def test_non_square_tile(self):
        """Edge tiles may be non-square (e.g., 256x240)."""
        tw, th = 256, 240
        raw = _make_yuyv(180, 128, 180, 128) * (tw * th // 2)
        rgb = yuyv_to_rgb(raw, tile_width=tw, tile_height=th)
        assert rgb.shape == (th, tw, 3)

    def test_pixel_pair_independence(self):
        """Verify that the two pixels within a YUYV pair are decoded correctly."""
        # Pixel 0: Y=100, shared U=150, V=180
        # Pixel 1: Y=200, shared U=150, V=180
        raw = _make_yuyv(100, 150, 200, 180)  # Exactly 2 pixels
        rgb = yuyv_to_rgb(raw, tile_width=2, tile_height=1)
        assert rgb.shape == (1, 2, 3)

        # The two pixels should differ since they have different Y
        assert rgb[0, 0, 0] != rgb[0, 1, 0]  # R channels differ

    def test_clipping(self):
        """Values outside 0-255 should be clipped, not wrapped."""
        # Extreme Cr=255, Y=128 -> R = 128 + 1.402*127 = 306 → clip to 255
        # Extreme Cb=0, Y=128 -> B = 128 + 1.772*(-128) = -99 → clip to 0
        raw = _make_yuyv(128, 0, 128, 255) * (4 * 4 // 2)
        rgb = yuyv_to_rgb(raw, tile_width=4, tile_height=4)
        # Check no over/underflow
        assert rgb.min() >= 0
        assert rgb.max() <= 255
        # At least some pixels should hit the extremes
        assert rgb[:, :, 0].max() >= 250  # R clipped high
        assert rgb[:, :, 2].min() <= 5    # B clipped low
