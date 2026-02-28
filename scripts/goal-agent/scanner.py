"""
Goal Scanner — reads vision board goal files and builds a prioritized work queue
of incomplete tasks.
"""

import os
import re
import yaml
from datetime import datetime, date
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Task:
    description: str
    goal_name: str
    goal_title: str
    goal_dir: str
    goal_index_path: str
    deadline: str | None = None
    priority: int = 0  # lower = higher priority


@dataclass
class Goal:
    name: str
    title: str
    directory: str
    index_path: str
    status: str
    deadline: str | None
    confidence: str
    description: str
    tasks: list[Task] = field(default_factory=list)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and body from markdown content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        meta = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        meta = {}

    body = parts[2].strip()
    return meta, body


def extract_tasks(body: str) -> list[str]:
    """Find all unchecked task items (- [ ]) in the markdown body."""
    return re.findall(r"^- \[ \] (.+)$", body, re.MULTILINE)


def extract_title(body: str) -> str:
    """Extract the first H1 heading from the body."""
    match = re.search(r"^# (.+)$", body, re.MULTILINE)
    return match.group(1) if match else "Untitled"


def extract_goal_description(body: str) -> str:
    """Extract the Goal section content."""
    match = re.search(
        r"^## Goal\s*\n+(.*?)(?=\n## |\Z)", body, re.MULTILINE | re.DOTALL
    )
    if match:
        return match.group(1).strip()
    # Fallback: use first paragraph after the title
    lines = [l for l in body.split("\n") if l.strip() and not l.startswith("#")]
    return lines[0] if lines else ""


def calculate_priority(deadline: str | None, status: str) -> int:
    """
    Lower number = higher priority.
    - Tasks with deadlines get priority based on days remaining
    - In-progress tasks get a boost
    - No deadline = low priority
    """
    priority = 100

    if deadline:
        try:
            dl = datetime.strptime(str(deadline), "%Y-%m-%d").date()
            days_left = (dl - date.today()).days
            priority = max(0, days_left)
        except (ValueError, TypeError):
            pass

    if status == "in_progress":
        priority = max(0, priority - 10)

    return priority


def scan_goals(repo_root: str, year: str = "2026", month: str | None = None) -> list[Goal]:
    """
    Scan vision board goals for the given month and return a list of Goal objects
    with their incomplete tasks.
    """
    if month is None:
        month = datetime.now().strftime("%m")

    goals_dir = Path(repo_root) / "vision_boards" / year / month / "goals"

    if not goals_dir.exists():
        return []

    goals = []

    for goal_dir in sorted(goals_dir.iterdir()):
        if not goal_dir.is_dir():
            continue

        index_path = goal_dir / "index.md"
        if not index_path.exists():
            continue

        content = index_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(content)

        status = meta.get("status", "not_started")
        if status in ("completed", "failed"):
            continue

        deadline = meta.get("deadline")
        confidence = meta.get("confidence", "medium")
        title = extract_title(body)
        description = extract_goal_description(body)
        task_descriptions = extract_tasks(body)

        if not task_descriptions:
            continue

        goal = Goal(
            name=goal_dir.name,
            title=title,
            directory=str(goal_dir),
            index_path=str(index_path),
            status=status,
            deadline=str(deadline) if deadline else None,
            confidence=confidence,
            description=description,
            tasks=[],
        )

        for desc in task_descriptions:
            priority = calculate_priority(deadline, status)
            task = Task(
                description=desc,
                goal_name=goal_dir.name,
                goal_title=title,
                goal_dir=str(goal_dir),
                goal_index_path=str(index_path),
                deadline=str(deadline) if deadline else None,
                priority=priority,
            )
            goal.tasks.append(task)

        goals.append(goal)

    # Sort goals by priority (lowest number first = most urgent)
    goals.sort(key=lambda g: min(t.priority for t in g.tasks) if g.tasks else 999)

    return goals


def build_work_queue(goals: list[Goal], max_tasks: int = 3) -> list[Task]:
    """
    Build a flat work queue from goals, limited to max_tasks items.
    Picks the highest-priority task from each goal first, then fills remaining slots.
    """
    queue: list[Task] = []

    # One task per goal first (round-robin by priority)
    for goal in goals:
        if goal.tasks and len(queue) < max_tasks:
            best = min(goal.tasks, key=lambda t: t.priority)
            queue.append(best)

    # Fill remaining slots with next-highest-priority tasks across all goals
    if len(queue) < max_tasks:
        all_remaining = []
        for goal in goals:
            for task in goal.tasks:
                if task not in queue:
                    all_remaining.append(task)
        all_remaining.sort(key=lambda t: t.priority)
        for task in all_remaining:
            if len(queue) >= max_tasks:
                break
            queue.append(task)

    return queue


if __name__ == "__main__":
    import json
    import sys

    repo_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    month = sys.argv[2] if len(sys.argv) > 2 else None

    goals = scan_goals(repo_root, month=month)
    queue = build_work_queue(goals)

    print(f"Found {len(goals)} active goals with incomplete tasks:")
    for goal in goals:
        print(f"  [{goal.status}] {goal.title} ({len(goal.tasks)} tasks, deadline: {goal.deadline or 'none'})")

    print(f"\nWork queue ({len(queue)} tasks):")
    for i, task in enumerate(queue, 1):
        print(f"  {i}. [{task.goal_name}] {task.description} (priority: {task.priority})")

    # Output as JSON for the workflow
    queue_data = [
        {
            "description": t.description,
            "goal_name": t.goal_name,
            "goal_title": t.goal_title,
            "goal_dir": t.goal_dir,
            "goal_index_path": t.goal_index_path,
            "deadline": t.deadline,
            "priority": t.priority,
        }
        for t in queue
    ]
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as f:
            f.write(f"queue={json.dumps(queue_data)}\n")
            f.write(f"task_count={len(queue)}\n")
