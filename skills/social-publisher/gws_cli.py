"""Thin wrapper around the gws CLI for Sheets and Drive operations."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

import config


class GwsError(RuntimeError):
    pass


def _filter_stdout(stdout: str) -> str:
    lines = [
        line
        for line in stdout.splitlines()
        if line.strip() and "keyring backend" not in line.lower()
    ]
    return "\n".join(lines)


def run_gws(*args: str, fmt: str = "json") -> Any:
    cmd = [config.GWS_BIN, *args, "--format", fmt]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        raise GwsError(
            f"gws command failed: {' '.join(cmd)}\n{stderr or stdout}"
        ) from exc

    output = _filter_stdout(result.stdout)
    if not output:
        return None
    if fmt == "json":
        return json.loads(output)
    return output


def read_sheet_range(spreadsheet_id: str, range_a1: str) -> list[list[str]]:
    data = run_gws(
        "sheets",
        "+read",
        "--spreadsheet",
        spreadsheet_id,
        "--range",
        range_a1,
    )
    if isinstance(data, dict):
        return data.get("values") or []
    if isinstance(data, list):
        return data
    return []


def update_sheet_range(
    spreadsheet_id: str,
    range_a1: str,
    values: list[list[str]],
) -> None:
    params = json.dumps(
        {
            "spreadsheetId": spreadsheet_id,
            "range": range_a1,
            "valueInputOption": "USER_ENTERED",
        }
    )
    body = json.dumps({"values": values})
    run_gws(
        "sheets",
        "spreadsheets",
        "values",
        "update",
        "--params",
        params,
        "--json",
        body,
    )


def download_drive_file(file_id: str, output_path: str) -> str:
    params = json.dumps({"fileId": file_id, "alt": "media"})
    out_dir = os.path.dirname(os.path.abspath(output_path))
    filename = os.path.basename(output_path)
    os.makedirs(out_dir, exist_ok=True)
    # gws requires --output to resolve inside the process cwd
    cmd = [
        config.GWS_BIN,
        "drive",
        "files",
        "get",
        "--params",
        params,
        "--output",
        filename,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True, cwd=out_dir)
    except subprocess.CalledProcessError as exc:
        raise GwsError(
            f"Drive download failed for {file_id}: {(exc.stderr or exc.stdout or '').strip()}"
        ) from exc
    return output_path
