"""Tests for shared batch output planning policy."""

from pathlib import Path

from svs_to_ometiff.batch_plan import (
    find_duplicate_output_paths,
    normalized_output_path,
    output_path_for_input,
)


def test_output_path_for_input_defaults_to_source_folder():
    assert output_path_for_input("/slides/A01.svs", None) == "/slides/A01.ome.tiff"


def test_output_path_for_input_uses_explicit_output_dir():
    assert output_path_for_input("/slides/A01.svs", "/converted") == "/converted/A01.ome.tiff"


def test_duplicate_stems_collide_in_same_output_dir():
    duplicates = find_duplicate_output_paths(
        ["/run1/A01.svs", "/run2/A01.svs", "/run2/B01.svs"],
        "/converted",
    )

    assert duplicates == {
        "/converted/A01.ome.tiff": ["/run1/A01.svs", "/run2/A01.svs"]
    }


def test_normalized_output_path_casefolds_resolved_path(tmp_path):
    out = tmp_path / "Slide.ome.tiff"

    assert normalized_output_path(str(out)) == str(out.resolve()).casefold()


def test_duplicate_detection_uses_casefolded_output_paths(tmp_path):
    output_dir = tmp_path / "converted"
    output_dir.mkdir()

    duplicates = find_duplicate_output_paths(
        ["/run1/Slide.svs", "/run2/slide.svs"],
        str(output_dir),
    )

    expected_path = str(Path(output_dir) / "Slide.ome.tiff")
    assert duplicates == {expected_path: ["/run1/Slide.svs", "/run2/slide.svs"]}
