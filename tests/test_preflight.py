"""Disk-space preflight estimation tests."""

from pathlib import Path

import pytest

from svs_to_ometiff.preflight import (
    PreflightError,
    check_preflight,
    estimate_full_res_rgb_bytes,
    estimate_pyramid_rgb_bytes,
)


def test_estimate_full_res_rgb_bytes_from_dimensions() -> None:
    assert estimate_full_res_rgb_bytes(width=10, height=20) == 10 * 20 * 3


def test_estimate_pyramid_rgb_bytes_includes_requested_levels() -> None:
    assert estimate_pyramid_rgb_bytes(
        width=16,
        height=16,
        num_levels=3,
        downsample_factor=2,
    ) == (16 * 16 * 3) + (8 * 8 * 3) + (4 * 4 * 3)


def test_check_preflight_applies_safety_factor(tmp_path: Path) -> None:
    def fake_disk_usage(path: str):
        return (1_000_000, 0, 1_000_000)

    result = check_preflight(
        width=10,
        height=10,
        output_path=tmp_path / "out.ome.tiff",
        temp_dir=tmp_path,
        num_levels=1,
        downsample_factor=2,
        safety_factor=1.5,
        disk_usage=fake_disk_usage,
    )

    assert result.full_res_rgb_bytes == 300
    assert result.required_temp_bytes == 450
    assert result.required_output_bytes == 450
    assert result.pass_ is True


def test_check_preflight_passes_when_space_is_available(tmp_path: Path) -> None:
    def fake_disk_usage(path: str):
        return (1_000_000, 0, 1_000_000)

    result = check_preflight(
        width=100,
        height=100,
        output_path=tmp_path / "out.ome.tiff",
        temp_dir=tmp_path,
        num_levels=2,
        downsample_factor=2,
        safety_factor=1.2,
        disk_usage=fake_disk_usage,
    )

    assert result.pass_ is True
    assert result.errors == []


def test_check_preflight_fails_when_temp_space_is_insufficient(tmp_path: Path) -> None:
    def fake_disk_usage(path: str):
        return (1_000_000, 0, 1)

    with pytest.raises(PreflightError) as exc_info:
        check_preflight(
            width=100,
            height=100,
            output_path=tmp_path / "out.ome.tiff",
            temp_dir=tmp_path,
            num_levels=2,
            downsample_factor=2,
            safety_factor=1.2,
            disk_usage=fake_disk_usage,
        )

    assert "Insufficient temp space" in str(exc_info.value)
    assert "Use --temp-dir on a larger local SSD" in str(exc_info.value)
