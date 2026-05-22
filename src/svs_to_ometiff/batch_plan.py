"""Shared batch output planning policy for CLI and GUI adapters."""

from pathlib import Path
from typing import Optional


def output_path_for_input(svs_path: str, output_dir: Optional[str]) -> str:
    """Return the planned OME-TIFF output path for one source SVS path."""
    stem = Path(svs_path).stem
    if output_dir is not None:
        return str(Path(output_dir) / f"{stem}.ome.tiff")
    return str(Path(svs_path).parent / f"{stem}.ome.tiff")


def normalized_output_path(path: str) -> str:
    """Return a case-insensitive absolute key for output collision checks."""
    return str(Path(path).resolve()).casefold()


def find_duplicate_output_paths(
    files: list[str],
    output_dir: Optional[str],
) -> dict[str, list[str]]:
    """Return planned output paths that would be written by multiple inputs."""
    outputs: dict[str, tuple[str, list[str]]] = {}
    for svs_path in files:
        out_path = output_path_for_input(svs_path, output_dir)
        key = normalized_output_path(out_path)
        if key not in outputs:
            outputs[key] = (out_path, [])
        outputs[key][1].append(svs_path)

    return {
        out_path: input_paths
        for out_path, input_paths in outputs.values()
        if len(input_paths) > 1
    }
