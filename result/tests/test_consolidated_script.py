"""Smoke tests for the standalone single-file command-line converter."""

import subprocess
import sys
from pathlib import Path


def test_standalone_script_writes_html_beside_input(
    tmp_path: Path,
    sample_mhtml_data: bytes,
) -> None:
    """Run the script outside the result directory and check its default path."""
    input_path = tmp_path / "standalone.mhtml"
    output_path = input_path.with_suffix(".html")
    input_path.write_bytes(sample_mhtml_data)
    script_path = Path(__file__).parents[1] / "mhtml_converter_consolidated.py"

    completed = subprocess.run(
        [sys.executable, str(script_path), str(input_path), "--log-level", "ERROR"],
        check=False,
        capture_output=True,
        cwd=tmp_path,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.is_file()
    assert "Hello World" in output_path.read_text(encoding="utf-8")
    assert str(output_path) in completed.stdout
