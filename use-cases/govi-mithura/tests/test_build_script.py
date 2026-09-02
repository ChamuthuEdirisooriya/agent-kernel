"""Regression tests for the documented setup script."""

from pathlib import Path


def test_build_script_reuses_the_environment_and_keeps_the_lockfile_frozen() -> None:
    lines = (Path(__file__).parents[1] / "build.sh").read_text(encoding="utf-8").splitlines()

    create_environment = lines.index("uv venv --allow-existing")
    sync_dependencies = lines.index("uv sync --frozen")

    assert create_environment < sync_dependencies
