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

# Matches "- Status: PASS" / "- Status: FAIL" / "- Status: BLOCKER" / "- Status: MAJOR" / "- Status: MINOR" / "- Status: ADVISORY" / "- Status: NOT_APPLICABLE" / "- Status: N/A"
_STATUS_RE = re.compile(
    r"^-\s*Status:\s*(PASS|FAIL|BLOCKER|MAJOR|MINOR|ADVISORY|NOT_APPLICABLE|N/A)\s*$",
    re.IGNORECASE,
)

# Matches summary lines: "- Pass: 198" / "- Fail: 0" / "- Blocker: 0" / "- Major: 2" / "- Minor: 5" / "- Advisory: 0" / "- Not_Applicable: 10"
_SUMMARY_RE = re.compile(
    r"^-\s*(Pass|Fail|Blocker|Major|Minor|Advisory|Not_Applicable|N/A):\s*(\d+)\s*$",
    re.IGNORECASE,
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

    Each question is {id, text, status, severity, disposition, notes, artifact, fix, evidence}.
    """
    lines = md.splitlines()
    summary: dict[str, int] = {}
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
                "severity": "",
                "disposition": "",
                "notes": "",
                "artifact": "",
                "fix": "",
                "evidence": "",
            }
            continue

        # Status line
        stm = _STATUS_RE.match(line)
        if stm and cur_q is not None:
            st = stm.group(1).upper()
            if st == "N/A":
                st = "NOT_APPLICABLE"
            cur_q["status"] = st
            continue

        # Other fields (Severity, Disposition, Notes, Artifact, Fix, Evidence)
        if cur_q is not None and line.startswith("- "):
            field_line = line[2:].strip()
            if field_line.startswith("Severity:"):
                cur_q["severity"] = field_line[len("Severity:"):].strip().upper()
            elif field_line.startswith("Disposition:"):
                cur_q["disposition"] = field_line[len("Disposition:"):].strip().upper()
            elif field_line.startswith("Notes:"):
                cur_q["notes"] = field_line[len("Notes:"):].strip()
            elif field_line.startswith("Artifact:"):
                cur_q["artifact"] = field_line[len("Artifact:"):].strip()
            elif field_line.startswith("Fix:"):
                cur_q["fix"] = field_line[len("Fix:"):].strip()
            elif field_line.startswith("Evidence:"):
                cur_q["evidence"] = field_line[len("Evidence:"):].strip()

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
      3. No question has Status: FAIL or BLOCKER (or severity BLOCKER).
      4. Any MAJOR finding has an explicit Disposition: RESOLVED or ACCEPTED_AS_INTENDED.
      5. If a question bank is provided, every bank question ID is evaluated or marked NOT_APPLICABLE.
      6. Summary counts match actual statuses (if summary is present).
    """
    res = ValidationResult()
    data = parse_critique_report(report_md)
    questions = data["questions"]
    summary = data["summary"]

    if not questions:
        res.error("no questions parsed from critique report")
        return res

    bank_ids: set[str] = set()
    if question_bank_md:
        bank_ids = set(parse_question_bank(question_bank_md))

    report_ids: set[str] = set()
    counts: dict[str, int] = {
        "Pass": 0, "Fail": 0, "Blocker": 0, "Major": 0, "Minor": 0,
        "Advisory": 0, "Not_applicable": 0,
    }

    for q in questions:
        qid = q["id"]
        report_ids.add(qid)

        st = q["status"]
        sev = q["severity"]
        disp = q["disposition"]

        if not st:
            res.error(f"{qid}: missing 'Status:' line")
            continue

        # Tally counts
        c_key = st.capitalize()
        if c_key in counts:
            counts[c_key] += 1
        elif st == "NOT_APPLICABLE":
            counts["Not_applicable"] += 1

        # Check blocking conditions
        if st in ("FAIL", "BLOCKER") or sev == "BLOCKER":
            note = q["notes"] or q["fix"] or "hard blocker violated"
            tag = "FAIL" if st == "FAIL" else "BLOCKER"
            res.error(f"{qid} [{tag}]: {note[:100]}")
        elif st == "MAJOR" or sev == "MAJOR":
            if disp in ("RESOLVED", "ACCEPTED_AS_INTENDED", "OVERRIDDEN"):
                res.warn(f"{qid} [MAJOR - {disp}]: {q['notes'][:80]}")
            else:
                res.error(
                    f"{qid} [MAJOR]: requires Disposition: RESOLVED or ACCEPTED_AS_INTENDED (found '{disp or 'NONE'}')"
                )
        elif st in ("MINOR", "ADVISORY") or sev in ("MINOR", "ADVISORY"):
            if q["notes"]:
                res.warn(f"{qid} [{st}]: {q['notes'][:80]}")
        elif st in ("PASS", "NOT_APPLICABLE"):
            pass

    # Check question bank coverage
    if bank_ids:
        missing = bank_ids - report_ids
        if missing:
            res.error(
                f"{len(missing)} question(s) from the bank are missing in the "
                f"report: {sorted(missing)[:10]}{'...' if len(missing) > 10 else ''}"
            )

    # Check summary counts if present
    if summary:
        for k, v in summary.items():
            norm_k = k.capitalize()
            if norm_k in counts and counts[norm_k] != v:
                res.error(
                    f"summary {k} ({v}) != parsed count ({counts[norm_k]})"
                )

    return res
