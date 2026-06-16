#!/usr/bin/env python3
"""
utils.py — Shared helpers for log output and subprocess execution.
"""

import subprocess


def log(emoji: str, msg: str):
    """Print a log line with emoji prefix."""
    print(f"{emoji} {msg}", flush=True)


def run_cmd(cmd: str, timeout: int = 30) -> dict:
    """Run a shell command and return dict with stdout, stderr, code."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip(), "code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": "Command timed out", "code": -1}
