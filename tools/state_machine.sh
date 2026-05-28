#!/bin/bash
# tools/state_machine.sh — Deterministic state machine for worker loop
#
# Called by the worker BEFORE each action. Reads DEVPLAN frontmatter +
# environment variables set by run-iteration.sh. Outputs what to do next.
#
# Environment variables (set by run-iteration.sh via prompt or export):
#   STEP_BUDGET           — max actions this invocation (default 1)
#   STOP_BEFORE_REVIEW    — "true" to stop before entering review (default "false")
#
# Output (two lines to stdout):
#   ACTION: PLAN|EXECUTE|REVIEW|CLOSE|EXIT
#   NEXT: plan|execute|review|close
#
# The worker reads ACTION (what to do) and NEXT (what state to write to
# DEVPLAN frontmatter after completing the action). On EXIT, NEXT is the
# current state — no write needed.
#
# For CLOSE, the script sets blocked=true in DEVPLAN itself. The worker
# does not need to handle blocked writes.
#
# Usage:
#   output=$(bash tools/state_machine.sh)
#   action=$(echo "$output" | grep '^ACTION:' | awk '{print $2}')
#   next=$(echo "$output" | grep '^NEXT:' | awk '{print $2}')

set -euo pipefail

DEVPLAN="${DEVPLAN_PATH:-DEVPLAN.md}"
STEP_BUDGET="${STEP_BUDGET:-1}"
STOP_BEFORE_REVIEW="${STOP_BEFORE_REVIEW:-false}"

# --- Read frontmatter ---
blocked=$(grep '^blocked:' "$DEVPLAN" | head -1 | awk '{print $2}')
state=$(grep '^state:' "$DEVPLAN" | head -1 | awk '{print $2}')
steps_remaining=$(grep '^steps_remaining:' "$DEVPLAN" | head -1 | awk '{print $2}')
phase=$(grep '^phase:' "$DEVPLAN" | head -1 | awk '{print $2}')

# --- Blocked check (before any writes) ---
if [ "$blocked" = "true" ] || [ "$blocked" = "awaiting-human-audit" ]; then
  echo "ACTION: EXIT"
  echo "NEXT: $state"
  exit 0
fi

# --- Cold start: initialize budget on first call only ---
# Empty steps_remaining means "not yet initialized this invocation."
# 0 means "budget exhausted" — do NOT reinitialize.
if [ -z "$steps_remaining" ]; then
  steps_remaining=$STEP_BUDGET
  sed -i "s/^steps_remaining:.*/steps_remaining: $steps_remaining/" "$DEVPLAN"
fi

# --- Budget check ---
if [ "$steps_remaining" -le 0 ]; then
  echo "ACTION: EXIT"
  echo "NEXT: $state"
  exit 0
fi

# --- Count unchecked steps in current phase section ---
# Scope grep to the section starting with "## Phase $phase" to avoid
# matching checkboxes from other phases or non-step sections.
count_unchecked() {
  local phase_pattern="## Phase ${phase}"
  # Extract from phase header to next h2 (or end of file), count unchecked
  sed -n "/^${phase_pattern}/,/^## /p" "$DEVPLAN" | grep -c '^- \[ \]' 2>/dev/null || echo "0"
}

# --- Handle execute with no remaining steps → transition to review ---
if [ "$state" = "execute" ]; then
  unchecked=$(count_unchecked)
  if [ "$unchecked" -eq 0 ]; then
    state="review"
    sed -i "s/^state:.*/state: review/" "$DEVPLAN"
  fi
fi

# --- Stop-before-review check ---
if [ "$STOP_BEFORE_REVIEW" = "true" ] && [ "$state" = "review" ]; then
  echo "ACTION: EXIT"
  echo "NEXT: review"
  exit 0
fi

# --- Compute action + next state ---
case "$state" in
  plan)
    action="PLAN"
    next="execute"
    ;;
  execute)
    action="EXECUTE"
    unchecked=$(count_unchecked)
    if [ "$unchecked" -le 1 ]; then
      next="review"
    else
      next="execute"
    fi
    ;;
  review)
    action="REVIEW"
    next="close"
    ;;
  close)
    action="CLOSE"
    next="close"
    # Close sets blocked — script owns this write
    sed -i "s/^blocked:.*/blocked: true/" "$DEVPLAN"
    ;;
  *)
    echo "ACTION: EXIT"
    echo "NEXT: $state"
    echo "ERROR: unknown state '$state'" >&2
    exit 1
    ;;
esac

# --- Decrement budget ---
steps_remaining=$((steps_remaining - 1))
sed -i "s/^steps_remaining:.*/steps_remaining: $steps_remaining/" "$DEVPLAN"

# --- Output ---
echo "ACTION: $action"
echo "NEXT: $next"
