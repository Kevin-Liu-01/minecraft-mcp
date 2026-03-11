from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_sim_startup_check() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "minecraft_dedalus_mcp.run_sim", "--skip-agent"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Ready: bridge http://127.0.0.1:8787, MCP http://127.0.0.1:8000/mcp" in result.stdout
    assert "Skipping Dedalus agent run by request." in result.stdout
