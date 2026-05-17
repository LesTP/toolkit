#!/usr/bin/env python3
"""Parse stream-json transcript from claude -p into human-readable summary.

Usage: python3 parse_jsonl.py < iteration.jsonl > iteration.txt
       python3 parse_jsonl.py --meta meta.tmp < iteration.jsonl > iteration.txt
"""
import sys
import json
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--meta', help='Write metadata to this file')
    args = parser.parse_args()

    result_text = ""
    cost = ""
    turns = ""
    duration = ""

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        t = obj.get("type", "")

        if t == "assistant":
            contents = obj.get("message", {}).get("content", [])
            for c in contents:
                if c.get("type") == "text":
                    print("ASSISTANT:", c["text"])
                elif c.get("type") == "tool_use":
                    name = c.get("name", "?")
                    keys = ", ".join(c.get("input", {}).keys())
                    print(f"TOOL CALL: {name}({keys})")

        elif t == "user":
            tur = obj.get("tool_use_result", {})
            if not isinstance(tur, dict):
                tur = {}
            finfo = tur.get("file", {})
            if not isinstance(finfo, dict):
                finfo = {}
            if finfo.get("filePath"):
                print(f"  -> Read {finfo['filePath']} ({finfo.get('numLines', '?')} lines)")
            else:
                contents = obj.get("message", {}).get("content", [])
                for c in contents:
                    if c.get("type") == "tool_result":
                        content_str = str(c.get("content", ""))[:200]
                        if content_str:
                            print(f"  -> Result: {content_str}")

        elif t == "result":
            result_text = obj.get("result", "")
            raw_cost = obj.get("total_cost_usd", "")
            cost = f"{float(raw_cost):.2f}" if raw_cost != "" else ""
            turns = str(obj.get("num_turns", ""))
            dur_ms = obj.get("duration_ms", 0)
            duration = f"{int(dur_ms / 1000)}s" if dur_ms else ""
            print(f"\n=== RESULT ===")
            print(f"Cost: ${cost} | Turns: {turns} | Duration: {duration}")
            for rline in result_text.strip().split("\n")[-10:]:
                print(rline)

    if args.meta:
        with open(args.meta, "w") as f:
            f.write(f"RESULT_TEXT={json.dumps(result_text)}\n")
            f.write(f"COST={cost}\n")
            f.write(f"TURNS={turns}\n")
            f.write(f"DURATION={duration}\n")

if __name__ == "__main__":
    main()
