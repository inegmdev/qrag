#!/usr/bin/env python3
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

iteration = 0
while True:
    iteration += 1
    print(f"\n--- ralph iteration {iteration} ---", flush=True)

    proc = subprocess.Popen(
        ["claude", "--dangerously-skip-permissions", "--print", PROMPT],
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
    )

    done = False
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        if SENTINEL in line:
            done = True

    proc.wait()

    if proc.returncode != 0:
        print(f"\nralph: claude exited with code {proc.returncode}, stopping.", flush=True)
        sys.exit(proc.returncode)

    if done:
        print(f"\nralph: all tasks done after {iteration} iteration(s).", flush=True)
        sys.exit(0)
