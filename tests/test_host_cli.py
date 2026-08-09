"""Tests for the Linux host installer and management CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_installer_help() -> None:
    result = _run("bash", "install.sh", "--help")
    assert result.returncode == 0
    assert "Debian, Ubuntu, and Raspberry Pi OS" not in result.stderr
    assert "--config PATH" in result.stdout


def test_host_tool_versions_match_manifest() -> None:
    cli_result = _run("bash", "pi/nwrctl", "version")
    installer_result = _run("bash", "install.sh", "version")
    manifest = json.loads(
        (ROOT / "custom_components/nwr_sdr/manifest.json").read_text()
    )
    assert cli_result.returncode == 0
    assert cli_result.stdout.strip() == f"nwrctl {manifest['version']}"
    assert installer_result.returncode == 0
    assert installer_result.stdout.strip() == f"nwr-install {manifest['version']}"


def test_cli_rejects_unknown_command() -> None:
    result = _run("bash", "pi/nwrctl", "not-a-command")
    assert result.returncode == 2
    assert "unknown command" in result.stderr
