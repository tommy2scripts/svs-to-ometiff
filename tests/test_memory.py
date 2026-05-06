"""Informative memory profiling tests for synthetic conversions."""

from pathlib import Path
import os
import threading
import time

import pytest
import tifffile

from svs_to_ometiff import ConvertConfig, convert
from helpers import write_synthetic_33007_svs

psutil = pytest.importorskip("psutil")


def _measure_peak_rss_delta(func):
    process = psutil.Process()
    baseline = process.memory_info().rss
    peak = baseline
    stop = threading.Event()

    def sample() -> None:
        nonlocal peak
        while not stop.is_set():
            peak = max(peak, process.memory_info().rss)
            time.sleep(0.001)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    try:
        result = func()
    finally:
        stop.set()
        sampler.join(timeout=1)
        peak = max(peak, process.memory_info().rss)

    return result, max(0, peak - baseline)


@pytest.mark.parametrize(
    ("width", "height", "num_levels"),
    [
        (128, 128, 2),
        (512, 512, 3),
    ],
)
def test_conversion_peak_memory_is_profiled_for_synthetic_inputs(
    tmp_path: Path,
    width: int,
    height: int,
    num_levels: int,
) -> None:
    input_svs = tmp_path / f"synthetic-{width}x{height}.svs"
    output_ometiff = tmp_path / f"synthetic-{width}x{height}.ome.tiff"
    write_synthetic_33007_svs(input_svs, width=width, height=height)

    def run_conversion():
        return convert(
            ConvertConfig(
                input_svs=str(input_svs),
                output_ometiff=str(output_ometiff),
                tile_size=16,
                compression=None,
                num_levels=num_levels,
                verbose=False,
            )
        )

    result, peak_delta = _measure_peak_rss_delta(run_conversion)
    target = int(1.2 * width * height * 3)

    print(
        f"memory_profile width={width} height={height} "
        f"levels={num_levels} peak_delta={peak_delta} target={target}"
    )

    assert result["pyramid_shapes"][0] == (height, width, 3)
    with tifffile.TiffFile(output_ometiff) as tif:
        assert tif.is_ome
        assert len(tif.series[0].levels) == num_levels

    if os.environ.get("SVS_OMETIFF_STRICT_MEMORY") == "1":
        assert peak_delta < target
