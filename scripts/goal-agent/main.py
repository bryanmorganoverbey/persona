"""
Goal Agent — main orchestrator.

Scans vision board goals for incomplete tasks, executes them via MiniMax API,
reports results back to the repo, and notifies via Telegram.

State machine with two phases:
  1. CLARIFICATION PHASE — if a pending clarification exists, poll Telegram
     for the user's reply and re-execute the blocked task with the answer.
  2. EXECUTION PHASE — scan goals, pick tasks, execute via LLM, save results.
     If a task needs clarification, send the question to Telegram and save state.
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from scanner import scan_goals, build_work_queue
from executor import execute_task
from reporter import (
    create_attempt_file,
    update_attempt_with_results,
    save_result_files,
    check_off_task,
    update_goal_status,
    git_commit_and_push,
)
from telegram import (
    notify_task_started,
    notify_task_completed,
    notify_task_failed,
    ask_clarification,
    notify_run_summary,
    get_replies_since,
    send_message,
)


MAX_TASKS_PER_RUN = int(os.environ.get("GOAL_AGENT_MAX_TASKS", "1"))
MAX_BUDGET_USD = float(os.environ.get("GOAL_AGENT_MAX_BUDGET_USD", "5.0"))
STALE_HOURS = int(os.environ.get("GOAL_AGENT_STALE_HOURS", "24"))


# ---------------------------------------------------------------------------
# Clarification state management
# ---------------------------------------------------------------------------

def _clarification_path(repo_root: str) -> Path:
    return Path(repo_root) / "scripts" / "goal-agent" / "clarifications.json"


def load_clarification(repo_root: str) -> dict | None:
    path = _clarification_path(repo_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_clarification(repo_root: str, state: dict) -> None:
    path = _clarification_path(repo_root)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def clear_clarification(repo_root: str) -> None:
    path = _clarification_path(repo_root)
    if path.exists():
        path.unlink()


def _is_stale(state: dict) -> bool:
    sent_at = state.get("sent_at", "")
    if not sent_at:
        return False
    try:
        sent_time = datetime.fromisoformat(sent_at)
        elapsed = (datetime.now(timezone.utc) - sent_time).total_seconds() / 3600
        return elapsed > STALE_HOURS
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Clarification reply handler
# ---------------------------------------------------------------------------

def handle_pending_clarification(repo_root: str, state: dict, remaining_budget: float) -> dict:
    """
    Check Telegram for a reply to a pending clarification question.
    If found, re-execute the blocked task with the user's answer injected.

    Returns stats dict with keys: answered, completed, failed, cost_usd.
    """
    stats = {"answered": False, "completed": 0, "failed": 0, "cost_usd": 0.0}

    message_id = state.get("message_id")
    task = state.get("task")
    question = state.get("question", "")

    if not message_id or not task:
        print("Invalid clarification state — clearing")
        clear_clarification(repo_root)
        return stats

    print(f"Checking for reply to clarification (message {message_id})...")
    print(f"  Task: {task.get('description', '?')}")
    print(f"  Question: {question[:100]}...")

    replies = get_replies_since(message_id)

    if not replies:
        if _is_stale(state):
            print("Clarification is stale (>24h) — clearing and moving on")
            send_message(
                f"*Goal Agent*\n\nNo reply received for clarification on "
                f"_{task.get('description', 'task')}_. Moving on."
            )
            clear_clarification(repo_root)
        else:
            print("No reply yet — keeping state, will check next run")
        return stats

    user_answer = "\n\n".join(replies)
    print(f"Got reply ({len(replies)} message(s), {len(user_answer)} chars)")
    stats["answered"] = True

    # Re-execute the task with the user's answer
    print(f"\n--- Re-executing with clarification: {task['description']} ---")
    notify_task_started(task)

    attempt_path = create_attempt_file(task, f"Re-attempt with user clarification:\n\n> {user_answer[:500]}", task["goal_dir"])
    git_commit_and_push(repo_root, f"goal-agent: re-attempt [{task['goal_name']}] with clarification")

    try:
        result = execute_task(task, remaining_budget=remaining_budget, user_answer=user_answer)
        stats["cost_usd"] += result.get("cost_usd", 0.0)

        if result.get("budget_exceeded", False):
            print("  Budget exceeded during re-execution")
            update_attempt_with_results(attempt_path, result, status="budget_exceeded")
            git_commit_and_push(repo_root, "goal-agent: budget limit reached during clarification re-attempt")
            clear_clarification(repo_root)
            return stats

        if result["needs_clarification"]:
            # Still needs more info — send a follow-up question
            print("  Still needs clarification — sending follow-up")
            update_attempt_with_results(attempt_path, result, status="blocked")
            new_msg_id = ask_clarification(task, result["clarification_question"] or "See attempt file for details.")
            if new_msg_id:
                save_clarification(repo_root, {
                    "message_id": new_msg_id,
                    "task": task,
                    "question": result["clarification_question"] or "",
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                clear_clarification(repo_root)
        else:
            # Success
            update_attempt_with_results(attempt_path, result, status="completed")
            save_result_files(task["goal_dir"], task, result)

            checked = check_off_task(task["goal_index_path"], task["description"])
            if checked:
                print("  Checked off task in goal index")
                update_goal_status(task["goal_index_path"])

            summary_lines = result["result"].split("\n")
            summary = next(
                (l for l in summary_lines if l.strip() and not l.startswith("#")),
                "Task completed successfully.",
            )
            notify_task_completed(task, summary)
            stats["completed"] += 1
            clear_clarification(repo_root)

        git_commit_and_push(
            repo_root,
            f"goal-agent: clarification results for [{task['goal_name']}] {task['description']}",
        )

    except Exception as e:
        print(f"  FAILED during re-execution: {e}")
        traceback.print_exc()
        notify_task_failed(task, str(e))
        stats["failed"] += 1
        clear_clarification(repo_root)
        git_commit_and_push(
            repo_root,
            f"goal-agent: failed re-attempt for [{task['goal_name']}] {task['description']}",
        )

    return stats


def run(repo_root: str, month: str | None = None) -> dict:
    """
    Main execution loop.

    1. Check for pending clarifications (reply phase)
    2. Scan for incomplete goals
    3. Build a prioritized work queue
    4. For each task: plan → execute → report
    5. If blocked: send question to Telegram, save clarification state
    6. Commit results and notify
    """
    print(f"=== Goal Agent Run: {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Repo root: {repo_root}")
    print(f"Max tasks per run: {MAX_TASKS_PER_RUN}")
    print(f"Budget limit: ${MAX_BUDGET_USD:.2f}")

    stats = {"attempted": 0, "completed": 0, "failed": 0, "blocked": 0}
    cumulative_cost = 0.0

    # -----------------------------------------------------------------------
    # Phase 1: Handle pending clarification
    # -----------------------------------------------------------------------
    pending = load_clarification(repo_root)
    if pending:
        print(f"\nPending clarification found (sent {pending.get('sent_at', 'unknown')})")
        remaining = MAX_BUDGET_USD - cumulative_cost
        clar_stats = handle_pending_clarification(repo_root, pending, remaining)
        cumulative_cost += clar_stats.get("cost_usd", 0.0)
        stats["completed"] += clar_stats.get("completed", 0)
        stats["failed"] += clar_stats.get("failed", 0)
        if clar_stats.get("answered"):
            stats["attempted"] += 1

        # If clarification is still pending (no reply yet), skip to summary
        if load_clarification(repo_root) is not None:
            print("\nClarification still pending — skipping normal execution")
            print(f"\n=== Run Complete ===")
            notify_run_summary(**stats)
            return stats
    else:
        print("\nNo pending clarifications")

    # -----------------------------------------------------------------------
    # Phase 2: Normal execution
    # -----------------------------------------------------------------------

    if cumulative_cost >= MAX_BUDGET_USD:
        print(f"\nBudget exhausted after clarification phase — skipping new tasks")
        notify_run_summary(**stats)
        return stats

    # Scan
    goals = scan_goals(repo_root, month=month)
    print(f"\nFound {len(goals)} active goals:")
    for g in goals:
        print(f"  - {g.title} ({len(g.tasks)} tasks, status: {g.status})")

    if not goals:
        print("No incomplete goals found. Nothing to do.")
        notify_run_summary(**stats)
        return stats

    # Build work queue
    queue = build_work_queue(goals, max_tasks=MAX_TASKS_PER_RUN)
    print(f"\nWork queue ({len(queue)} tasks):")
    for i, t in enumerate(queue, 1):
        print(f"  {i}. [{t.goal_name}] {t.description}")

    # Execute each task
    for i, task in enumerate(queue):
        if cumulative_cost >= MAX_BUDGET_USD:
            print(f"\n  Budget exhausted (${cumulative_cost:.4f} >= ${MAX_BUDGET_USD:.2f}). Stopping.")
            break

        if i > 0:
            print(f"\n  Cooling down 15s between tasks...")
            time.sleep(15)

        task_dict = {
            "description": task.description,
            "goal_name": task.goal_name,
            "goal_title": task.goal_title,
            "goal_dir": task.goal_dir,
            "goal_index_path": task.goal_index_path,
            "deadline": task.deadline,
        }

        print(f"\n--- Executing: {task.description} ---")
        stats["attempted"] += 1

        try:
            notify_task_started(task_dict)

            plan = f"Execute task: {task.description}\nGoal: {task.goal_title}\nUsing MiniMax API."
            attempt_path = create_attempt_file(task_dict, plan, task.goal_dir)
            print(f"  Created attempt: {attempt_path}")

            git_commit_and_push(
                repo_root,
                f"goal-agent: plan attempt for [{task.goal_name}] {task.description}",
            )

            remaining = MAX_BUDGET_USD - cumulative_cost
            result = execute_task(task_dict, remaining_budget=remaining)
            task_cost = result.get("cost_usd", 0.0)
            cumulative_cost += task_cost
            print(f"  Tokens used: {result['tokens_used']}")
            print(f"  Task cost: ${task_cost:.4f} | Cumulative: ${cumulative_cost:.4f} / ${MAX_BUDGET_USD:.2f}")

            if result.get("budget_exceeded", False):
                print(f"  BUDGET LIMIT REACHED — task skipped, saving progress")
                update_attempt_with_results(attempt_path, result, status="budget_exceeded")
                git_commit_and_push(
                    repo_root,
                    f"goal-agent: budget limit reached, saving progress",
                )
                break

            if result["needs_clarification"]:
                print(f"  BLOCKED — needs clarification")
                update_attempt_with_results(attempt_path, result, status="blocked")

                question_text = result["clarification_question"] or "See attempt file for details."
                msg_id = ask_clarification(task_dict, question_text)
                stats["blocked"] += 1

                if msg_id:
                    save_clarification(repo_root, {
                        "message_id": msg_id,
                        "task": task_dict,
                        "question": question_text,
                        "sent_at": datetime.now(timezone.utc).isoformat(),
                    })
                    print(f"  Saved clarification state (message_id: {msg_id})")

            else:
                update_attempt_with_results(attempt_path, result, status="completed")
                save_result_files(task.goal_dir, task_dict, result)

                checked = check_off_task(task.goal_index_path, task.description)
                if checked:
                    print(f"  Checked off task in goal index")
                    update_goal_status(task.goal_index_path)

                summary_lines = result["result"].split("\n")
                summary = next(
                    (l for l in summary_lines if l.strip() and not l.startswith("#")),
                    "Task completed successfully.",
                )
                notify_task_completed(task_dict, summary)
                stats["completed"] += 1

            git_commit_and_push(
                repo_root,
                f"goal-agent: results for [{task.goal_name}] {task.description}",
            )

        except Exception as e:
            print(f"  FAILED: {e}")
            traceback.print_exc()
            notify_task_failed(task_dict, str(e))
            stats["failed"] += 1

            git_commit_and_push(
                repo_root,
                f"goal-agent: failed attempt for [{task.goal_name}] {task.description}",
            )

    # Summary
    print(f"\n=== Run Complete ===")
    print(f"Attempted: {stats['attempted']}")
    print(f"Completed: {stats['completed']}")
    print(f"Failed: {stats['failed']}")
    print(f"Blocked: {stats['blocked']}")
    print(f"Total cost: ${cumulative_cost:.4f} / ${MAX_BUDGET_USD:.2f}")

    notify_run_summary(**stats)

    return stats


if __name__ == "__main__":
    repo_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    month = sys.argv[2] if len(sys.argv) > 2 else None

    stats = run(repo_root, month=month)

    # Exit with error if all tasks failed
    if stats["attempted"] > 0 and stats["completed"] == 0 and stats["blocked"] == 0:
        print("ERROR: No tasks completed successfully")
        sys.exit(1)
