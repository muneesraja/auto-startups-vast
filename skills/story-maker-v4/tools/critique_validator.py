"""Deterministic validator for critique_report.md (GATE 0 enforcement).

Parses the critique agent's markdown report and verifies:
  1. Every question ID from the question bank has a ``### Q...`` entry.
  2. No ``Status: FAIL`` remains (all failures must be fixed).
  3. Summary counts match the actual statuses in the report.

No LLM calls. Pure parsing + assertions. Used by ``scripts/validate.py`` via
the ``critique`` schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .validators import ValidationResult


# Matches "### Q1.1 — Does every scene have a visible goal?"
_QUESTION_HEADER_RE = re.compile(r"^###\s+(Q\d+\.\d+)\s*[—-]\s*(.*)$")

# Matches "- Status: PASS" / "- Status: FAIL" / "- Status: ADVISORY"
_STATUS_RE = re.compile(r"^-\s*Status:\s*(PASS|FAIL|ADVISORY)\s*$", re.IGNORECASE)

# Matches summary lines: "- Pass: 198" / "- Fail: 17" / "- Advisory: 0"
_SUMMARY_RE = re.compile(
    r"^-\s*(Pass|Fail|Advisory):\s*(\d+)\s*$", re.IGNORECASE
)

# Matches question IDs in the question bank: "### Q1.1 — ..."
_BANK_QUESTION_RE = re.compile(r"^###\s+(Q\d+\.\d+)\s*[—-]\s*(.*)$")


def parse_question_bank(bank_md: str) -> list[str]:
    """Extract all question IDs from the question bank markdown.

    Returns a list like ['Q1.1', 'Q1.2', ..., 'Q7.25'].
    """
    ids: list[str] = []
    for line in bank_md.splitlines():
        m = _BANK_QUESTION_RE.match(line)
        if m:
            ids.append(m.group(1))
    return ids


def parse_critique_report(md: str) -> dict:
    """Parse critique_report.md -> {summary, questions: [...]}.

    Each question is {id, text, status, notes, artifact, fix}.
    """
    lines = md.splitlines()
    summary: dict[str, int] = {"Pass": 0, "Fail": 0, "Advisory": 0}
    questions: list[dict] = []
    cur_q: dict | None = None

    for line in lines:
        # Summary section
        sm = _SUMMARY_RE.match(line)
        if sm:
            key = sm.group(1).capitalize()
            summary[key] = int(sm.group(2))
            continue

        # Question header
        qm = _QUESTION_HEADER_RE.match(line)
        if qm:
            if cur_q is not None:
                questions.append(cur_q)
            cur_q = {
                "id": qm.group(1),
                "text": qm.group(2).strip(),
                "status": "",
                "notes": "",
                "artifact": "",
                "fix": "",
            }
            continue

        # Status line
        stm = _STATUS_RE.match(line)
        if stm and cur_q is not None:
            cur_q["status"] = stm.group(1).upper()
            continue

        # Other fields (Notes, Artifact, Fix) — collect as raw text
        if cur_q is not None and line.startswith("- "):
            field_line = line[2:].strip()
            if field_line.startswith("Notes:"):
                cur_q["notes"] = field_line[len("Notes:"):].strip()
            elif field_line.startswith("Artifact:"):
                cur_q["artifact"] = field_line[len("Artifact:"):].strip()
            elif field_line.startswith("Fix:"):
                cur_q["fix"] = field_line[len("Fix:"):].strip()

    if cur_q is not None:
        questions.append(cur_q)

    return {"summary": summary, "questions": questions}


def validate_critique_report(
    report_md: str,
    question_bank_md: str | None = None,
) -> ValidationResult:
    """Validate a critique report.

    Checks:
      1. At least one question is present.
      2. Every question has a Status line.
      3. No question has Status: FAIL.
      4. If a question bank is provided, every bank question ID is in the report.
      5. Summary counts match actual statuses (if summary is present).
    """
    res = ValidationResult()
    data = parse_critique_report(report_md)
    questions = data["questions"]
    summary = data["summary"]

    if not questions:
        res.error("no questions parsed from critique report")
        return res

    # Check every question has a status
    bank_ids: set[str] = set()
    if question_bank_md:
        bank_ids = set(parse_question_bank(question_bank_md))

    report_ids: set[str] = set()
    fail_count = 0
    pass_count = 0
    advisory_count = 0

    for q in questions:
        qid = q["id"]
        report_ids.add(qid)

        if not q["status"]:
            res.error(f"{qid}: missing 'Status:' line")
            continue

        if q["status"] == "FAIL":
            fail_count += 1
            if not q["fix"]:
                res.error(f"{qid}: FAIL but missing 'Fix:' line")
            if not q["artifact"]:
                res.error(f"{qid}: FAIL but missing 'Artifact:' line")
            res.error(f"{qid}: Status is FAIL — {q['notes'][:80]}")
        elif q["status"] == "PASS":
            pass_count += 1
        elif q["status"] == "ADVISORY":
            advisory_count += 1

    # Check all bank questions are in the report
    if bank_ids:
        missing = bank_ids - report_ids
        if missing:
            res.error(
                f"{len(missing)} question(s) from the bank are missing in the "
                f"report: {sorted(missing)[:10]}{'...' if len(missing) > 10 else ''}"
            )

    # Check summary counts match (if summary is present)
    if any(summary.values()):
        if summary.get("Pass", 0) != pass_count:
            res.error(
                f"summary Pass ({summary['Pass']}) != actual pass count ({pass_count})"
            )
        if summary.get("Fail", 0) != fail_count:
            res.error(
                f"summary Fail ({summary['Fail']}) != actual fail count ({fail_count})"
            )
        if summary.get("Advisory", 0) != advisory_count:
            res.error(
                f"summary Advisory ({summary['Advisory']}) != actual advisory count ({advisory_count})"
            )

    return res
