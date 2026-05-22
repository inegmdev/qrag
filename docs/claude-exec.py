#!/usr/bin/env python3
import json
import subprocess
import sys

SENTINEL = "!!!ALL TASKS DONE!!!"

PROMPT = (
    "@docs/PRD.md @issues/INDEX.md @docs/progress.txt "
    "1. Read the PRD and progress file. "
    "2. Find the next incomplete task and implement it. "
    "3. Commit your changes. "
    "4. Update @docs/progress.txt with what you did. "
    "ONLY DO ONE TASK AT A TIME."
    "IF THERE IS NO MORE INCOMPLETE TASKS, THEN PRINT `!!!ALL TASKS DONE!!!`"
)


def run_claude():
    proc = subprocess.Popen(
        [
            "claude",
            "--dangerously-skip-permissions",
            "--print",
            "--output-format", "stream-json",
            "--verbose",
            PROMPT,
        ],
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )

    accumulated = ""
    done = False

    for raw in proc.stdout:
        raw = raw.strip()
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            sys.stdout.write(raw + "\n")
            sys.stdout.flush()
            continue

        etype = event.get("type")

        if etype == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    text = block["text"]
                    sys.stdout.write(text)
                    sys.stdout.flush()
                    accumulated += text
                    if SENTINEL in accumulated:
                        done = True

        elif etype == "result":
            result_text = event.get("result", "")
            if result_text and result_text not in accumulated:
                sys.stdout.write(result_text)
                sys.stdout.flush()
                accumulated += result_text
                if SENTINEL in accumulated:
                    done = True

    proc.wait()
    return proc.returncode, done


iteration = 0
while True:
    iteration += 1
    print(f"\n--- ralph iteration {iteration} ---", flush=True)

    returncode, done = run_claude()

    if returncode != 0:
        print(f"\nralph: claude exited with code {returncode}, stopping.", flush=True)
        sys.exit(returncode)

    if done:
        print(f"\nralph: all tasks done after {iteration} iteration(s).", flush=True)
        sys.exit(0)
