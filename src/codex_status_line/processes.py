"""Find the Codex process running inside a tmux pane, using `ps` so it works on Linux and macOS."""

import subprocess
import time

ETIME_CLOCK_FIELDS = 3  # hours, minutes, seconds


def list_processes():
    """Return (pid, parent pid, command name) for every process."""
    output = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,comm="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    table = []
    for line in output.splitlines():
        pid, parent_pid, command = line.split(None, 2)
        table.append((int(pid), int(parent_pid), command.strip()))
    return table


def find_descendant_named(process_table, root_pid, name):
    """Breadth-first search from root_pid (included) for a process whose command is `name`.

    Codex can sit under the pane's shell, or under an npm wrapper under the shell.
    """
    children_by_parent = {}
    command_by_pid = {}
    for pid, parent_pid, command in process_table:
        children_by_parent.setdefault(parent_pid, []).append(pid)
        command_by_pid[pid] = command
    queue = [root_pid]
    while queue:
        pid = queue.pop(0)
        # macOS ps prints the full path as the command name, so compare the last part.
        if command_by_pid.get(pid, "").rsplit("/", 1)[-1] == name:
            return pid
        queue.extend(children_by_parent.get(pid, []))
    return None


def parse_elapsed_time(text):
    """Turn ps etime output, [[days-]hours:]minutes:seconds, into seconds."""
    text = text.strip()
    days = 0
    if "-" in text:
        day_text, text = text.split("-", 1)
        days = int(day_text)
    fields = [int(value) for value in text.split(":")]
    while len(fields) < ETIME_CLOCK_FIELDS:
        fields.insert(0, 0)
    hours, minutes, seconds = fields
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def process_start_time(pid):
    output = subprocess.run(
        ["ps", "-o", "etime=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return time.time() - parse_elapsed_time(output)
