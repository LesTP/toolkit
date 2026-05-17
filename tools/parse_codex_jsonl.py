#!/usr/bin/env python3
"""Parse Codex exec JSONL transcript into human-readable summary.

Usage: python3 parse_codex_jsonl.py < iteration.jsonl > iteration.txt
       python3 parse_codex_jsonl.py --meta meta.tmp < iteration.jsonl > iteration.txt

Codex JSONL event types:
  thread.started  — session info (thread_id)
  turn.started    — marks beginning of a turn
  item.started    — command beginning (command_execution)
  item.completed  — agent_message (text) or command_execution (command, output, exit_code)
  turn.completed  — usage stats (input_tokens, output_tokens, cached_input_tokens)
"""
import sys
import json
import argparse


def truncate(s, max_len=300):
    if len(s) <= max_len:
        return s
    return s[:max_len] + f"... [{len(s)} chars total]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--meta', help='Write metadata to this file')
    args = parser.parse_args()

    result_text = ""
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    item_count = 0
    last_message = ""

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        t = obj.get("type", "")

        if t == "thread.started":
            tid = obj.get("thread_id", "?")
            print(f"=== Thread: {tid} ===")

        elif t == "turn.started":
            print("\n--- Turn started ---")

        elif t == "item.completed":
            item = obj.get("item", {})
            item_type = item.get("type", "")
            item_count += 1

            if item_type == "agent_message":
                text = item.get("text", "")
                last_message = text
                print(f"\nASSISTANT: {text}")

            elif item_type == "command_execution":
                cmd = item.get("command", "")
                output = item.get("aggregated_output", "")
                exit_code = item.get("exit_code")
                status = item.get("status", "")

                # Strip the /bin/bash -lc wrapper for readability
                if cmd.startswith('/bin/bash -lc '):
                    cmd = cmd[len('/bin/bash -lc '):]
                    if cmd.startswith('"') and cmd.endswith('"'):
                        cmd = cmd[1:-1]
                    elif cmd.startswith("'") and cmd.endswith("'"):
                        cmd = cmd[1:-1]

                status_tag = ""
                if status == "failed" or (exit_code is not None and exit_code != 0):
                    status_tag = f" [FAILED, exit={exit_code}]"

                print(f"\n$ {cmd}{status_tag}")
                if output.strip():
                    print(truncate(output.rstrip()))

        elif t == "turn.completed":
            usage = obj.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cached_tokens = usage.get("cached_input_tokens", 0)
            print(f"\n--- Turn completed ---")
            print(f"Tokens: {input_tokens} in ({cached_tokens} cached), {output_tokens} out")

    # The last agent_message typically contains the loop signal
    result_text = last_message

    if args.meta:
        with open(args.meta, "w") as f:
            f.write(f"RESULT_TEXT={json.dumps(result_text)}\n")
            f.write(f"COST=n/a\n")
            f.write(f"TURNS={item_count}\n")
            f.write(f"DURATION=\n")
            f.write(f"INPUT_TOKENS={input_tokens}\n")
            f.write(f"OUTPUT_TOKENS={output_tokens}\n")
            f.write(f"CACHED_TOKENS={cached_tokens}\n")


if __name__ == "__main__":
    main()
