#!/bin/bash
# run-iteration.sh — Execute autonomous loop iterations
# Called by the orchestrator (TG bot session) or standalone.
#
# SETUP: Set PROJECT_DIR below to your project's absolute path.
#
# Usage:
#   bash run-iteration.sh                       # single iteration, Claude backend
#   bash run-iteration.sh --backend codex       # single iteration, Codex backend
#   bash run-iteration.sh -n 5                  # run up to 5 iterations (stops on ESCALATE)
#   bash run-iteration.sh -n 5 --start 3        # start from iteration 3
#   bash run-iteration.sh --model opus          # single iteration, Opus model
#   bash run-iteration.sh --backend codex -n 3  # 3 Codex iterations
#   bash run-iteration.sh --multi-step 5        # one invocation, up to 5 steps
#   bash run-iteration.sh --multi-step 10 --to-review  # stop before review
#
# Output:
#   logs/loop/iteration_NNN.jsonl  — full stream-json transcript (Claude) or JSONL (Codex)
#   logs/loop/iteration_NNN.txt    — human-readable summary
#   logs/loop/summary.log          — one line per iteration
#
# Exit: 0=normal, 1=blocked/phase-boundary, 2=error
#
# Dependencies: python3 (for JSON parsing), claude CLI or codex CLI

set -uo pipefail

# Guard: Codex logs_1.sqlite grows unboundedly and causes OOM at ~100MB.
# At 97MB on disk, Codex CLI inflated it to 13+GB in RAM (~130x).
# Delete if over 1MB — Codex recreates it fresh. Project's own logging
# (summary.log, iteration JSONL/TXT, DEVLOG) is the real audit trail.
CODEX_LOG_DB="$HOME/.codex/logs_1.sqlite"
if [[ -f "$CODEX_LOG_DB" ]]; then
  SIZE_KB=$(du -k "$CODEX_LOG_DB" | cut -f1)
  if [[ $SIZE_KB -gt 1024 ]]; then
    echo "[guard] Codex logs_1.sqlite is ${SIZE_KB}KB (>1MB) — deleting to prevent OOM"
    rm -f "$CODEX_LOG_DB" "$CODEX_LOG_DB-shm" "$CODEX_LOG_DB-wal"
  fi
fi

# ============================================================
# CUSTOMIZE: Set this to your project's absolute path
# ============================================================
PROJECT_DIR="/home/claude/workspace/toolkit"
# ============================================================

LOG_DIR="$PROJECT_DIR/logs/loop"
SUMMARY_FILE="$LOG_DIR/summary.log"

# Parse arguments
MAX_ITERATIONS=1
START_ITER=""
BACKEND="claude"
MODEL="sonnet"
MULTI_STEP=0
TO_REVIEW=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--iterations) MAX_ITERATIONS="$2"; shift 2 ;;
    --start)         START_ITER="$2"; shift 2 ;;
    --backend)       BACKEND="$2"; shift 2 ;;
    --model)         MODEL="$2"; shift 2 ;;
    --multi-step)    MULTI_STEP="$2"; shift 2 ;;
    --to-review)     TO_REVIEW=true; shift ;;
    *)               echo "Unknown option: $1"; exit 2 ;;
  esac
done

# Validate backend
case $BACKEND in
  claude|codex) ;;
  *) echo "Unknown backend: $BACKEND (must be claude or codex)"; exit 2 ;;
esac

# Auto-determine start iteration from summary log
if [[ -z "$START_ITER" ]]; then
  if [[ -f "$SUMMARY_FILE" ]]; then
    LAST=$(grep -oP 'iter=\K[0-9]+' "$SUMMARY_FILE" | tail -1)
    START_ITER=$(( ${LAST:-0} + 1 ))
  else
    START_ITER=1
  fi
fi

# Backend-neutral prompt — references the adapter file by backend name
case $BACKEND in
  claude) ADAPTER_FILE="CLAUDE.md" ;;
  codex)  ADAPTER_FILE="CODEX.md" ;;
esac

PROMPT="MANDATORY FIRST STEP: Read ${ADAPTER_FILE} now. It contains references to WORKER_SPEC.md and project documents — read all of them before doing anything else.

You are a stateless worker. You have no memory of previous iterations. Reconstruct all state from files.

After reading ${ADAPTER_FILE} and its references, enter the main loop from WORKER_SPEC \u00a73: call bash tools/state_machine.sh before each action."

# Export env vars for state_machine.sh
export STEP_BUDGET=$MULTI_STEP
if [[ $STEP_BUDGET -lt 1 ]]; then STEP_BUDGET=1; fi
export STEP_BUDGET
export STOP_BEFORE_REVIEW="$TO_REVIEW"
export DEVPLAN_PATH="$PROJECT_DIR/DEVPLAN.md"

# Add STEP_BUDGET and STOP_BEFORE_REVIEW to prompt so the worker knows
# the values (for reference only — the script reads env vars directly)
if [[ $STEP_BUDGET -gt 1 ]]; then
  PROMPT="$PROMPT

STEP_BUDGET: $STEP_BUDGET"
fi

if [[ "$STOP_BEFORE_REVIEW" == "true" ]]; then
  PROMPT="$PROMPT

STOP_BEFORE_REVIEW: true"
fi

# Add JSONL path for per-step turn health check (Codex only)
if [[ "$BACKEND" == "codex" ]]; then
  ITER_PAD_PROMPT=$(printf "%03d" "${START_ITER:-1}")
  JSONL_PATH="$LOG_DIR/iteration_${ITER_PAD_PROMPT}.jsonl"
  PROMPT="$PROMPT

ITERATION_JSONL: $JSONL_PATH"
fi

PROMPT="$PROMPT

Your final output MUST end with exactly these five lines — no text after:
EXIT: 0 | 1 | 2
REASON: <one line — what was done or why stopping>
ACTION_TYPE: PLAN | EXECUTE | REVIEW | CLOSE
ACTION_ID: <phase.step>
STEPS_COMPLETED: <number of actions performed in this invocation>"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR"

FINAL_EXIT=0
ITER=$START_ITER
END_ITER=$(( START_ITER + MAX_ITERATIONS - 1 ))

while [[ $ITER -le $END_ITER ]]; do
  ITER_PAD=$(printf "%03d" "$ITER")
  JSONL_FILE="$LOG_DIR/iteration_${ITER_PAD}.jsonl"
  TXT_FILE="$LOG_DIR/iteration_${ITER_PAD}.txt"
  META_FILE="$LOG_DIR/.iteration_meta.tmp"
  LAST_MSG_FILE="$LOG_DIR/.last_message.tmp"

  echo "=== Iteration $ITER ($BACKEND) — $(date -Iseconds) ==="

  # Reset steps_remaining so state_machine.sh reinitializes from STEP_BUDGET.
  # Without this, a stale value from a previous invocation or manual edit
  # overrides the --multi-step budget (state_machine.sh only initializes
  # steps_remaining when it is empty, not when it is 0).
  sed -i 's/^steps_remaining:.*/steps_remaining:/' "$PROJECT_DIR/DEVPLAN.md"

  case $BACKEND in
    claude)
      claude -p "$PROMPT" \
        --dangerously-skip-permissions \
        --model "$MODEL" \
        --max-budget-usd 10.00 \
        --output-format stream-json \
        --verbose \
        2>&1 > "$JSONL_FILE"
      EXIT_CODE=$?

      # Parse jsonl: generate human-readable transcript + extract metadata
      python3 "$PROJECT_DIR/tools/parse_jsonl.py" --meta "$META_FILE" < "$JSONL_FILE" > "$TXT_FILE"

      # Read metadata
      COST="" ; TURNS="" ; DURATION=""
      if [[ -f "$META_FILE" ]]; then
        COST=$(grep '^COST=' "$META_FILE" | cut -d= -f2)
        TURNS=$(grep '^TURNS=' "$META_FILE" | cut -d= -f2)
        DURATION=$(grep '^DURATION=' "$META_FILE" | cut -d= -f2)
        RESULT_TEXT=$(grep '^RESULT_TEXT=' "$META_FILE" | cut -d= -f2- | python3 -c "import sys,json; print(json.loads(sys.stdin.read()))" 2>/dev/null || echo "")
        rm -f "$META_FILE"
      fi
      ;;

    codex)
      START_TIME=$(date +%s)

      codex exec "$PROMPT" \
        --dangerously-bypass-approvals-and-sandbox \
        -o "$LAST_MSG_FILE" \
        --json \
        2>&1 > "$JSONL_FILE"
      EXIT_CODE=$?

      END_TIME=$(date +%s)
      DURATION=$(( END_TIME - START_TIME ))s

      # Extract last message as the result text
      RESULT_TEXT=""
      if [[ -f "$LAST_MSG_FILE" ]]; then
        RESULT_TEXT=$(cat "$LAST_MSG_FILE")
        rm -f "$LAST_MSG_FILE"
      fi

      # Generate human-readable transcript from JSONL using dedicated parser
      if [[ -f "$JSONL_FILE" ]]; then
        python3 "$PROJECT_DIR/tools/parse_codex_jsonl.py" --meta "$META_FILE" < "$JSONL_FILE" > "$TXT_FILE"
      fi

      # Read metadata from parser
      if [[ -f "$META_FILE" ]]; then
        TURNS=$(grep '^TURNS=' "$META_FILE" | cut -d= -f2)
        RESULT_TEXT_META=$(grep '^RESULT_TEXT=' "$META_FILE" | cut -d= -f2- | python3 -c "import sys,json; print(json.loads(sys.stdin.read()))" 2>/dev/null || echo "")
        # Prefer -o file result, fall back to parser-extracted last message
        if [[ -z "$RESULT_TEXT" && -n "$RESULT_TEXT_META" ]]; then
          RESULT_TEXT="$RESULT_TEXT_META"
        fi
        rm -f "$META_FILE"
      fi

      COST="n/a"
      ;;
  esac

  # Extract signal fields from result text (works for both backends)
  EXIT_SIGNAL=$(echo "$RESULT_TEXT" | grep -oP 'EXIT: \K[0-2]' || echo "")
  REASON=$(echo "$RESULT_TEXT" | grep -oP 'REASON: \K.+' || echo "")
ACTION_TYPE=$(echo "$RESULT_TEXT" | grep -oP 'ACTION_TYPE: \K\w+' || echo "")
  ACTION_ID=$(echo "$RESULT_TEXT" | grep -oP 'ACTION_ID: \K\S+' || echo "")
  STEPS_COMPLETED=$(echo "$RESULT_TEXT" | grep -oP 'STEPS_COMPLETED: \K[0-9]+' || echo "1")

  # Map EXIT code to legacy signal for summary.log compatibility
  case "$EXIT_SIGNAL" in
    0) SIGNAL="OK" ;;
    1) SIGNAL="BLOCKED" ;;
    2) SIGNAL="ERROR" ;;
    *) SIGNAL="" ;;
  esac

  # Write summary line
  TIMESTAMP=$(date -Iseconds)
  echo "$TIMESTAMP | iter=$ITER | backend=$BACKEND | signal=$SIGNAL | exit=$EXIT_CODE | cost=\$$COST | turns=$TURNS | duration=$DURATION | action=$ACTION_TYPE | id=$ACTION_ID | steps=$STEPS_COMPLETED | reason=$REASON" >> "$SUMMARY_FILE"

  # Print summary to stdout for orchestrator
  echo "Backend=$BACKEND | Signal=$SIGNAL | Cost=\$$COST | Turns=$TURNS | Duration=$DURATION | Steps=$STEPS_COMPLETED"
  echo "Action: $ACTION_TYPE ($ACTION_ID)"
  echo "Reason: $REASON"

  # Track the last iter that actually ran — used for accurate post-loop reporting
  # regardless of whether the loop exits naturally or via break below.
  LAST_RAN=$ITER

  # Decide whether to continue — read DEVPLAN state
  if [[ -z "$EXIT_SIGNAL" ]]; then
    echo "=== NO SIGNAL at iteration $ITER — ERROR STOP ==="
    FINAL_EXIT=2
    break
  elif [[ "$EXIT_SIGNAL" == "2" ]]; then
    echo "=== ERROR at iteration $ITER (action=$ACTION_TYPE): $REASON ==="
    FINAL_EXIT=2
    break
  elif [[ "$EXIT_SIGNAL" == "1" ]]; then
    echo "=== BLOCKED at iteration $ITER: $REASON ==="
    FINAL_EXIT=1
    break
  else
    # EXIT 0 — check DEVPLAN for blocked (phase boundary)
    BLOCKED=$(grep '^blocked:' "$PROJECT_DIR/DEVPLAN.md" | head -1 | sed 's/blocked:[[:space:]]*//')
    if [[ "$BLOCKED" == "true" ]]; then
      echo "=== Phase-boundary at iteration $ITER (awaiting human audit): $REASON ==="
      FINAL_EXIT=0
      break
    fi
  fi

  echo "=== Iteration $ITER complete ==="
  ITER=$(( ITER + 1 ))
done

echo "=== Stopped after iteration ${LAST_RAN:-$START_ITER} ==="
exit $FINAL_EXIT
