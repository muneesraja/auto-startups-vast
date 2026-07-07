#!/usr/bin/env python3
"""Create or refresh the Social Publisher Google Sheet layout, README tab, and colors."""

from __future__ import annotations

import json
import os
import sys

_SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _SKILL_DIR)

import config  # noqa: E402
from gws_cli import run_gws, update_sheet_range  # noqa: E402

SHEET_ID = config.SHEET_ID or os.getenv("SOCIAL_PUBLISHER_SHEET_ID", "")

README_ROWS = [
    ["Social Publisher — Quick Guide"],
    [""],
    ["COLOR LEGEND"],
    ["Light blue columns", "YOU FILL IN — video metadata, Drive IDs, platforms"],
    ["Light amber column", "AGENT MANAGES — status (don't edit while publishing)"],
    ["Light green columns", "AUTO-FILLED — post URLs and errors after publish"],
    [""],
    ["ASK THE AGENT (examples)"],
    ["Publish one row", "Use social-publisher to upload queue row episode-03 to YouTube."],
    ["Dry-run first", "Dry-run social-publisher for row episode-03 — don't upload yet."],
    ["Publish Instagram", "Publish row episode-03 to Instagram (needs HTTPS on VPS)."],
    ["Exchange IG token", "Run exchange_instagram_token.py then publish row episode-03 to Instagram."],
    ["All pending", "Publish all pending rows in this sheet to YouTube."],
    ["After story-maker", "Add a queue row for this Drive video and publish to YouTube as unlisted."],
    ["Check status", "What happened with row episode-02? Read errors and yt_url/ig_url."],
    [""],
    ["INSTAGRAM TOKEN"],
    ["IG_SHORT_LIVED_TOKEN", "Meta dashboard → Generate token (~1 hour)"],
    ["IG_APP_SECRET", "Meta dashboard → Instagram app secret"],
    ["IG_ACCESS_TOKEN", "Long-lived token — run exchange_instagram_token.py on VPS"],
    ["IG_USER_ID", "Account ID shown under username in dashboard (e.g. 17841431826663169)"],
    [""],
    ["FULL AGENT GUIDE", "See skills/social-publisher/README.md in the repo"],
    [""],
    ["COLUMN NOTES"],
    ["drive_file_id", "Raw Google Drive file ID for final_film.mp4"],
    ["thumbnail_drive_file_id", "Optional Drive ID for thumbnail (jpg/png)"],
    ["platforms", "youtube | instagram | youtube,instagram"],
    ["visibility", "public | unlisted | private"],
    ["brand", "Must match Accounts tab"],
    [""],
    ["AI DISCLOSURE", "YouTube uploads always declare AI-generated / synthetic content."],
]

QUEUE_HEADERS = [
    "id",
    "brand",
    "drive_file_id",
    "thumbnail_drive_file_id",
    "title",
    "description",
    "hashtags",
    "platforms",
    "visibility",
    "status",
    "yt_url",
    "ig_url",
    "errors",
]

ACCOUNTS_HEADERS = [
    "brand",
    "platform",
    "account_ref",
    "credential_ref",
    "enabled",
]


def _batch_update(spreadsheet_id: str, requests: list[dict]) -> dict:
    params = json.dumps({"spreadsheetId": spreadsheet_id})
    body = json.dumps({"requests": requests})
    return run_gws(
        "sheets",
        "spreadsheets",
        "batchUpdate",
        "--params",
        params,
        "--json",
        body,
    )


def _get_spreadsheet(spreadsheet_id: str) -> dict:
    params = json.dumps({"spreadsheetId": spreadsheet_id})
    return run_gws("sheets", "spreadsheets", "get", "--params", params)


def _ensure_readme_tab(spreadsheet_id: str, sheets: list[dict]) -> int:
    for sheet in sheets:
        if sheet["properties"]["title"] == "README":
            return sheet["properties"]["sheetId"]
    result = _batch_update(
        spreadsheet_id,
        [{"addSheet": {"properties": {"title": "README", "index": 0}}}],
    )
    return result["replies"][0]["addSheet"]["properties"]["sheetId"]


def _color_cell(red: float, green: float, blue: float) -> dict:
    return {"red": red, "green": green, "blue": blue}


def _format_queue_tab(spreadsheet_id: str, queue_sheet_id: int) -> None:
    header_bg = _color_cell(0.10, 0.45, 0.91)
    header_fg = _color_cell(1, 1, 1)
    input_bg = _color_cell(0.85, 0.92, 0.97)
    status_bg = _color_cell(1.0, 0.95, 0.80)
    output_bg = _color_cell(0.85, 0.94, 0.85)

    requests = [
        # Header row bold + blue
        {
            "repeatCell": {
                "range": {
                    "sheetId": queue_sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 13,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": header_bg,
                        "textFormat": {"bold": True, "foregroundColor": header_fg},
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat)",
            }
        },
        # Input columns A-I (0-8)
        {
            "repeatCell": {
                "range": {
                    "sheetId": queue_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 200,
                    "startColumnIndex": 0,
                    "endColumnIndex": 9,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": input_bg}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        },
        # Status column J (9)
        {
            "repeatCell": {
                "range": {
                    "sheetId": queue_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 200,
                    "startColumnIndex": 9,
                    "endColumnIndex": 10,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": status_bg}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        },
        # Output columns K-M (10-12)
        {
            "repeatCell": {
                "range": {
                    "sheetId": queue_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 200,
                    "startColumnIndex": 10,
                    "endColumnIndex": 13,
                },
                "cell": {"userEnteredFormat": {"backgroundColor": output_bg}},
                "fields": "userEnteredFormat.backgroundColor",
            }
        },
        # Freeze header + first two columns
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": queue_sheet_id,
                    "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 2},
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        },
        # Wider columns for description / urls
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": queue_sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 5,
                    "endIndex": 6,
                },
                "properties": {"pixelSize": 280},
                "fields": "pixelSize",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": queue_sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 10,
                    "endIndex": 12,
                },
                "properties": {"pixelSize": 260},
                "fields": "pixelSize",
            }
        },
    ]
    _batch_update(spreadsheet_id, requests)


def _format_accounts_tab(spreadsheet_id: str, accounts_sheet_id: int) -> None:
    header_bg = _color_cell(0.10, 0.45, 0.91)
    header_fg = _color_cell(1, 1, 1)
    input_bg = _color_cell(0.85, 0.92, 0.97)
    _batch_update(
        spreadsheet_id,
        [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": accounts_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": header_bg,
                            "textFormat": {"bold": True, "foregroundColor": header_fg},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": accounts_sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 50,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                    "cell": {"userEnteredFormat": {"backgroundColor": input_bg}},
                    "fields": "userEnteredFormat.backgroundColor",
                }
            },
        ],
    )


def _format_readme_tab(spreadsheet_id: str, readme_sheet_id: int) -> None:
    title_bg = _color_cell(0.10, 0.45, 0.91)
    _batch_update(
        spreadsheet_id,
        [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": readme_sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": title_bg,
                            "textFormat": {"bold": True, "foregroundColor": _color_cell(1, 1, 1), "fontSize": 14},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": readme_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 220},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": readme_sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "properties": {"pixelSize": 520},
                    "fields": "pixelSize",
                }
            },
        ],
    )


def main() -> int:
    if not SHEET_ID:
        print("Set SOCIAL_PUBLISHER_SHEET_ID in .env", file=sys.stderr)
        return 1

    meta = _get_spreadsheet(SHEET_ID)
    sheets = meta.get("sheets", [])
    sheet_by_title = {s["properties"]["title"]: s["properties"]["sheetId"] for s in sheets}

    readme_id = _ensure_readme_tab(SHEET_ID, sheets)
    queue_id = sheet_by_title.get(config.QUEUE_TAB, 1077190066)
    accounts_id = sheet_by_title.get(config.ACCOUNTS_TAB, 811060478)

    update_sheet_range(SHEET_ID, "README!A1:B40", README_ROWS)
    update_sheet_range(SHEET_ID, f"{config.QUEUE_TAB}!A1:M1", [QUEUE_HEADERS])
    update_sheet_range(SHEET_ID, f"{config.ACCOUNTS_TAB}!A1:E1", [ACCOUNTS_HEADERS])

    _format_readme_tab(SHEET_ID, readme_id)
    _format_queue_tab(SHEET_ID, queue_id)
    _format_accounts_tab(SHEET_ID, accounts_id)

    print(f"Sheet updated: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
