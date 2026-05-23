#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import termios
import tty
from datetime import datetime

SENTINEL = "!!!ALL TASKS DONE!!!"

AI_CONFIGS = {
    "claude": {
        "cmd": "claude",
        "display_name": "Claude",
        "model": "haiku",
        "afk_params": ["--dangerously-skip-permissions"],
        "output_params": ["--print", "--output-format", "stream-json", "--verbose"],
        "efficiency_params": ["--model", "haiku", "--effort", "medium"],
    },
    "gemini": {
        "cmd": "gemini",
        "display_name": "Gemini",
        "model": "gemini-2.5-flash",
        "afk_params": ["--approval-mode", "yolo"],
        "output_params": ["--output-format", "stream-json", "-d"],
        "efficiency_params": ["-m", "gemini-2.5-flash"],
        "prompt_flag": "-p",
    },
    "opencode": {
        "cmd": "opencode",
        "display_name": "OpenCode",
        "model": "default",
        "afk_params": ["--dangerously-skip-permissions"],
        "output_params": ["run", "--format", "json"],
        "efficiency_params": [],
    },
}

PROMPT = (
    "@docs/PRD.md @issues/INDEX.md @docs/progress.txt "
    "1. Read the PRD and progress file. "
    "2. Find the next incomplete task and implement it. "
    "3. Commit your changes. "
    "4. Update @docs/progress.txt @issues/INDEX.md with what you did. "
    "ONLY DO ONE TASK AT A TIME. "
    "IF THERE IS NO MORE INCOMPLETE TASKS, THEN PRINT `!!!ALL TASKS DONE!!!`"
)


def _detect_available_ais() -> list[str]:
    available = []
    if shutil.which("gemini"):
        available.append("gemini")
    if shutil.which("claude"):
        available.append("claude")
    if shutil.which("opencode"):
        available.append("opencode")
    return available


def _select_ai_interactive(available: list[str]) -> str:
    if len(available) == 1:
        name = AI_CONFIGS[available[0]]["display_name"]
        print(f"→ Using {name} (only one AI detected)")
        return available[0]

    labels = [AI_CONFIGS[a]["display_name"] for a in available]

    if not sys.stdin.isatty():
        print("Available AI agents:")
        for i, label in enumerate(labels, 1):
            print(f"  {i}) {label}")
        try:
            while True:
                try:
                    choice = int(input(f"Select (1-{len(labels)}): "))
                    if 1 <= choice <= len(labels):
                        return available[choice - 1]
                except ValueError:
                    pass
                print(f"Enter a number between 1 and {len(labels)}")
        except EOFError:
            print(f"→ Defaulting to {labels[0]}")
            return available[0]

    selected = 0

    def _getch():
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = ch + sys.stdin.read(2)
                return seq
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    print("Select AI agent:\n")
    try:
        while True:
            sys.stdout.write("\033[?25l")
            for i, label in enumerate(labels):
                if i == selected:
                    sys.stdout.write(f"\033[7m  ▸ {label}  \033[0m\n")
                else:
                    sys.stdout.write(f"    {label}  \n")
            sys.stdout.write(f"\033[{len(labels)}A")
            sys.stdout.flush()

            key = _getch()
            if key == "\x1b[A":
                selected = (selected - 1) % len(labels)
            elif key == "\x1b[B":
                selected = (selected + 1) % len(labels)
            elif key in ("\r", "\n"):
                break
    finally:
        sys.stdout.write("\033[?25h")

    sys.stdout.write(f"\033[{len(labels)}B\033[J")
    sys.stdout.flush()

    return available[selected]


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _boxed_section(rows: list[tuple[str, str]]) -> str:
    width = 62
    sep = "═" * width
    out = [f"  ╔{sep}╗"]
    for title, val in rows:
        label = f"  {title}:"
        padded = f"{label} {val}"
        out.append(f"  ║  {padded:<{width-2}}║")
    out.append(f"  ╚{sep}╝")
    return "\n".join(out)


def print_banner(ai_name: str, ai_cfg: dict, start_time: datetime):
    rows = [
        ("AFK Session", ""),
        ("Started", start_time.strftime("%Y-%m-%d %H:%M:%S")),
        ("AI", ai_cfg["display_name"]),
        ("Model", ai_cfg["model"]),
        ("Directory", os.getcwd()),
    ]
    print()
    print(_boxed_section(rows))
    print()


def print_footer(ai_name: str, ai_cfg: dict, start_time: datetime, end_time: datetime, iterations: int, status: str):
    duration_secs = int((end_time - start_time).total_seconds())
    rows = [
        ("Session Complete", ""),
        ("Started", start_time.strftime("%Y-%m-%d %H:%M:%S")),
        ("Ended", end_time.strftime("%Y-%m-%d %H:%M:%S")),
        ("Duration", _format_duration(duration_secs)),
        ("AI", ai_cfg["display_name"]),
        ("Model", ai_cfg["model"]),
        ("Iterations", str(iterations)),
        ("Status", status),
    ]
    print()
    print(_boxed_section(rows))
    print()


def run_ai(ai_cfg: dict) -> tuple[int, bool]:
    prompt_flag = ai_cfg.get("prompt_flag")
    if prompt_flag:
        cmd = [
            ai_cfg["cmd"],
            *ai_cfg["afk_params"],
            *ai_cfg["output_params"],
            *ai_cfg["efficiency_params"],
            prompt_flag,
            PROMPT,
        ]
    else:
        cmd = [
            ai_cfg["cmd"],
            *ai_cfg["afk_params"],
            *ai_cfg["output_params"],
            *ai_cfg["efficiency_params"],
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
                sys.stderr.write(f"❌ Session limit reached. {raw}\n")
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

        elif etype == "text":
            text = event.get("part", {}).get("text", "")
            if text:
                sys.stdout.write(text)
                sys.stdout.flush()
                accumulated += text
                if SENTINEL in accumulated:
                    done = True

    stderr_output = proc.stderr.read().strip() if proc.stderr else ""
    proc.wait()

    if proc.returncode != 0:
        if stderr_output:
            sys.stderr.write(
                f"❌ {ai_cfg['display_name']} exit error "
                f"(code {proc.returncode}): {stderr_output}\n"
            )
        elif any("session limit" in line.lower() for line in text_lines):
            sys.stderr.write(
                f"❌ {ai_cfg['display_name']} exit error: "
                f"session limit reached.\n"
            )
        else:
            sys.stderr.write(
                f"❌ {ai_cfg['display_name']} exit error: "
                f"code {proc.returncode}.\n"
            )
        sys.stderr.flush()

    return proc.returncode, done


def main():
    available = _detect_available_ais()
    if not available:
        print("❌ No AI agents found. Install 'claude', 'gemini', or 'opencode' CLI.")
        print("   Claude:   https://docs.anthropic.com/en/docs/claude-code/overview")
        print("   Gemini:   https://github.com/google-gemini/gemini-cli")
        print("   OpenCode: https://opencode.ai")
        sys.exit(1)

    ai_name = _select_ai_interactive(available)
    ai_cfg = AI_CONFIGS[ai_name]

    start_time = datetime.now()
    print_banner(ai_name, ai_cfg, start_time)

    iteration = 0
    while True:
        iteration += 1
        print(f"\n{'─' * 60}", flush=True)
        print(f"  Iteration {iteration} — {ai_cfg['display_name']}", flush=True)
        print(f"{'─' * 60}", flush=True)

        returncode, done = run_ai(ai_cfg)

        if returncode != 0:
            msg = f"❌ Error (code {returncode})"
            print(f"\n{msg}", flush=True)
            end_time = datetime.now()
            print_footer(ai_name, ai_cfg, start_time, end_time, iteration, msg)
            sys.exit(returncode)

        if done:
            msg = "✅ All tasks done"
            print(f"\n{msg} after {iteration} iteration(s).", flush=True)
            end_time = datetime.now()
            print_footer(ai_name, ai_cfg, start_time, end_time, iteration, msg)
            sys.exit(0)


if __name__ == "__main__":
    main()
