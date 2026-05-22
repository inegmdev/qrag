#!/usr/bin/env python3
import os
import pty
import select
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
    """Run claude under a PTY so it streams output immediately (no pipe buffering)."""
    master_fd, slave_fd = pty.openpty()

    proc = subprocess.Popen(
        ["claude", "--dangerously-skip-permissions", "--print", PROMPT],
        stdout=slave_fd,
        stderr=slave_fd,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )
    os.close(slave_fd)

    buf = ""
    done = False
    while True:
        try:
            ready, _, _ = select.select([master_fd], [], [], 0.05)
        except (KeyboardInterrupt, SystemExit):
            proc.terminate()
            raise

        if ready:
            try:
                data = os.read(master_fd, 4096).decode("utf-8", errors="replace")
            except OSError:
                break
            sys.stdout.write(data)
            sys.stdout.flush()
            buf += data
            if SENTINEL in buf:
                done = True
        elif proc.poll() is not None:
            break

    os.close(master_fd)
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
