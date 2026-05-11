"""End-to-end CLI smoke test: inspect -> convert -> verify flow."""

from click.testing import CliRunner

from helpers import write_synthetic_33007_svs
from svs_to_ometiff.cli import main as convert_main
from svs_to_ometiff.inspect import main as inspect_main
from svs_to_ometiff.verify import main as verify_main


def test_cli_inspect_convert_verify_flow(tmp_path) -> None:
    """Validate the production path a user will actually follow."""
    source = tmp_path / "synthetic.svs"
    output = tmp_path / "synthetic.ome.tiff"
    write_synthetic_33007_svs(source, width=32, height=32)

    # Step 1: inspect
    inspect_result = CliRunner().invoke(inspect_main, [str(source)])
    assert inspect_result.exit_code == 0
    assert "Convertible: yes" in inspect_result.output

    # Step 2: convert (use --compression none and minimal levels for speed)
    convert_result = CliRunner().invoke(
        convert_main,
        [
            str(source),
            str(output),
            "--compression",
            "none",
            "--num-levels",
            "2",
            "--quiet",
        ],
    )
    assert convert_result.exit_code == 0
    assert output.exists()

    # Step 3: verify
    verify_result = CliRunner().invoke(verify_main, [str(output), "--min-levels", "2"])
    assert verify_result.exit_code == 0
    assert "PASS" in verify_result.output
