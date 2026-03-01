"""
Goal Reporter — writes attempt files, updates goal checklists, and handles
git commit/push for completed work.
"""

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def create_attempt_file(task: dict, plan: str, goal_dir: str) -> str:
    """
    Create an attempt file before execution starts.
    Returns the path to the created file.
    """
    attempts_dir = Path(goal_dir) / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    filename = f"{timestamp}-attempt.md"
    filepath = attempts_dir / filename

    content = f"""---
task: "{task['description']}"
goal: {task['goal_name']}
started: {datetime.now(timezone.utc).isoformat()}
status: in_progress
---

# Attempt: {task['description']}

## Plan

{plan}
"""
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def update_attempt_with_results(
    attempt_path: str,
    result: dict,
    status: str = "completed",
) -> None:
    """Update an existing attempt file with execution results."""
    content = Path(attempt_path).read_text(encoding="utf-8")

    # Update frontmatter status and add completion time
    content = content.replace("status: in_progress", f"status: {status}")

    completed_line = f"completed: {datetime.now(timezone.utc).isoformat()}"
    tokens_line = f"tokens_input: {result['tokens_used']['input']}"
    tokens_out_line = f"tokens_output: {result['tokens_used']['output']}"
    model_line = f"model: {result['model']}"

    # Insert after the started: line
    content = re.sub(
        r"(started: .+\n)",
        f"\\1{completed_line}\n{model_line}\n{tokens_line}\n{tokens_out_line}\n",
        content,
    )

    # Append results
    content += f"\n## Results\n\n{result['result']}\n"

    Path(attempt_path).write_text(content, encoding="utf-8")


def save_result_files(goal_dir: str, task: dict, result: dict) -> list[str]:
    """
    Save any deliverable files produced by the agent into the goal directory.
    Returns list of created file paths.
    """
    created_files = []

    # Save the main result as a findings file if substantial
    result_text = result["result"]
    if len(result_text) > 500:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        safe_name = re.sub(r"[^a-z0-9]+", "-", task["description"].lower())[:50]
        filename = f"{timestamp}-{safe_name}.md"
        filepath = Path(goal_dir) / filename

        filepath.write_text(
            f"# {task['description']}\n\n{result_text}\n", encoding="utf-8"
        )
        created_files.append(str(filepath))

    return created_files


def check_off_task(goal_index_path: str, task_description: str) -> bool:
    """
    Mark a task as complete in the goal's index.md by changing [ ] to [x].
    Returns True if the task was found and checked off.
    """
    path = Path(goal_index_path)
    content = path.read_text(encoding="utf-8")

    escaped = re.escape(task_description)
    pattern = rf"^- \[ \] {escaped}$"
    replacement = f"- [x] {task_description}"

    new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

    if count > 0:
        path.write_text(new_content, encoding="utf-8")
        return True
    return False


def update_goal_status(goal_index_path: str) -> str:
    """
    Check if all tasks in a goal are complete and update the frontmatter status.
    Returns the new status.
    """
    path = Path(goal_index_path)
    content = path.read_text(encoding="utf-8")

    incomplete = re.findall(r"^- \[ \]", content, re.MULTILINE)
    completed = re.findall(r"^- \[x\]", content, re.MULTILINE)

    if not incomplete and completed:
        new_status = "completed"
    elif completed:
        new_status = "in_progress"
    else:
        new_status = "not_started"

    content = re.sub(
        r"^status: .+$", f"status: {new_status}", content, flags=re.MULTILINE
    )
    path.write_text(content, encoding="utf-8")

    return new_status


def git_commit_and_push(repo_root: str, message: str) -> bool:
    """Stage all changes, commit locally, rebase on remote, and push."""
    try:
        subprocess.run(
            ["git", "config", "user.name", "Goal Agent"],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "goal-agent@persona.local"],
            cwd=repo_root, check=True, capture_output=True,
        )

        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_root, check=True, capture_output=True,
        )

        diff = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            cwd=repo_root, capture_output=True,
        )
        if diff.returncode == 0:
            return False

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_root, check=True, capture_output=True,
        )

        # Rebase our commit on top of any remote changes, then push
        subprocess.run(
            ["git", "pull", "origin", "main", "--rebase"],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=repo_root, check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e.stderr.decode() if e.stderr else e}")
        return False
