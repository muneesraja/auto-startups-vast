#!/usr/bin/env bash
# done_check.sh — Mark a STV task done if its expected output files exist.
#
# Usage:
#   done_check.sh <min_size_kb> <file1> [file2 ...]
#
# Behavior:
#   - Exits 0 (DONE) if ALL listed files exist AND each is >= min_size_kb.
#   - Exits 1 (NOT DONE) if any file is missing or too small.
#   - Prints a clear summary table on both paths.
#
# Why this exists:
#   The 2026-06-11 panda-pippin T3 run looped 185 times because the agent
#   had no objective "are we done yet?" check. After sheets were on disk,
#   the agent kept editing _rerender_v2.py in a never-ending loop.
#   This script gives the agent a hard, file-based success gate.
#
# Example (T3 character sheets):
#   bash done_check.sh 100 \
#     <story>/characters/pippin_reference_sheet.png \
#     <story>/characters/bamboo_reference_sheet.png \
#     && echo "T3 done" || echo "T3 not done"
#
# Example (T5 frames, expect 14 FF + 14 LF = 28 PNGs):
#   bash done_check.sh 50 <story>/scenes/01/ff.png <story>/scenes/01/lf.png ...

set -u
MIN_KB="${1:-100}"
shift

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <min_size_kb> <file1> [file2 ...]"
  echo "  Exits 0 if all files exist and are >= min_size_kb, else 1."
  exit 2
fi

ok=true
printf '%-10s %12s  %s\n' "STATUS" "SIZE_KB" "FILE"
printf '%-10s %12s  %s\n' "------" "-------" "----"

for f in "$@"; do
  if [ -f "$f" ]; then
    bytes=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f" 2>/dev/null || echo 0)
    kb=$(( bytes / 1024 ))
    if [ "$kb" -ge "$MIN_KB" ]; then
      printf '%-10s %12s  %s\n' "OK" "$kb" "$f"
    else
      printf '%-10s %12s  %s\n' "TOO_SMALL" "$kb" "$f"
      ok=false
    fi
  else
    printf '%-10s %12s  %s\n' "MISSING" "-" "$f"
    ok=false
  fi
done

if $ok; then
  echo ""
  echo "✅ DONE — all $# file(s) exist and are >= ${MIN_KB}KB"
  exit 0
else
  echo ""
  echo "❌ NOT DONE — fix the failures above and re-run."
  exit 1
fi
