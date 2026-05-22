#!/usr/bin/env python3
import json
import subprocess
import sys

SENTINEL = "!!!ALL TASKS DONE!!!"

AI_CMD = "claude"

AI_CMD_AFK_PARAMS_OPTIONS = [
    "--dangerously-skip-permissions",
]

AI_CMD_REALTIME_STDOUT_OUTPUT_OPTIONS = [
    "--print",
    "--output-format", "stream-json",
    "--verbose"
]

AI_CMD_LOWER_TOKEN_USAGE_OPTIONS = [
    "--model", "haiku",
    "--effort", "medium",
]

PROMPT = (
    "@docs/PRD.md @issues/INDEX.md @docs/progress.txt "
    "1. Read the PRD and progress file. "
    "2. Find the next incomplete task and implement it. "
    "3. Commit your changes. "
    "4. Update @docs/progress.txt @issues/INDEX.md with what you did. "
    "ONLY DO ONE TASK AT A TIME."
    "IF THERE IS NO MORE INCOMPLETE TASKS, THEN PRINT `!!!ALL TASKS DONE!!!`"
)


def run_claude():
    cmd = [
        AI_CMD,
        *AI_CMD_AFK_PARAMS_OPTIONS,
        *AI_CMD_REALTIME_STDOUT_OUTPUT_OPTIONS,
        *AI_CMD_LOWER_TOKEN_USAGE_OPTIONS,
        PROMPT,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    accumulated = ""
    done = False
    text_lines = []

    for raw in proc.stdout:
        raw = raw.strip()
        if not raw:
            continue
        text_lines.append(raw)
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            lower_raw = raw.lower()
            if "session limit" in lower_raw or "hit your session limit" in lower_raw:
                sys.stderr.write(f"❌ Claude error: session limit reached. {raw}\n")
            else:
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

    stderr_output = proc.stderr.read().strip() if proc.stderr else ""
    proc.wait()

    if proc.returncode != 0:
        if stderr_output:
            sys.stderr.write(f"❌ Claude exit error (code {proc.returncode}): {stderr_output}\n")
        elif any("session limit" in line.lower() for line in text_lines):
            sys.stderr.write("❌ Claude exit error: session limit reached. Please retry after the reset time.\n")
        else:
            sys.stderr.write(f"❌ Claude exit error: code {proc.returncode}.\n")
        sys.stderr.flush()

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
