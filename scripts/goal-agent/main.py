"""
Goal Agent — main orchestrator.

Scans vision board goals for incomplete tasks, executes them via Claude API,
reports results back to the repo, and notifies via Telegram.
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone

from scanner import scan_goals, build_work_queue
from executor import execute_task
from budget import BudgetExceededException
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
)


MAX_TASKS_PER_RUN = int(os.environ.get("GOAL_AGENT_MAX_TASKS", "1"))
MAX_BUDGET_USD = float(os.environ.get("GOAL_AGENT_MAX_BUDGET_USD", "5.0"))


def run(repo_root: str, month: str | None = None) -> dict:
    """
    Main execution loop.

    1. Scan for incomplete goals
    2. Build a prioritized work queue
    3. For each task: plan → execute → report
    4. Commit results and notify
    """
    print(f"=== Goal Agent Run: {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Repo root: {repo_root}")
    print(f"Max tasks per run: {MAX_TASKS_PER_RUN}")
    print(f"Budget limit: ${MAX_BUDGET_USD:.2f}")

    # Step 1: Scan
    goals = scan_goals(repo_root, month=month)
    print(f"\nFound {len(goals)} active goals:")
    for g in goals:
        print(f"  - {g.title} ({len(g.tasks)} tasks, status: {g.status})")

    if not goals:
        print("No incomplete goals found. Nothing to do.")
        return {"attempted": 0, "completed": 0, "failed": 0, "blocked": 0}

    # Step 2: Build work queue
    queue = build_work_queue(goals, max_tasks=MAX_TASKS_PER_RUN)
    print(f"\nWork queue ({len(queue)} tasks):")
    for i, t in enumerate(queue, 1):
        print(f"  {i}. [{t.goal_name}] {t.description}")

    # Step 3: Execute each task
    stats = {"attempted": 0, "completed": 0, "failed": 0, "blocked": 0}
    cumulative_cost = 0.0

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
            # Notify start
            notify_task_started(task_dict)

            # Create attempt file with plan
            plan = f"Execute task: {task.description}\nGoal: {task.goal_title}\nUsing Claude API with web search and code execution tools."
            attempt_path = create_attempt_file(task_dict, plan, task.goal_dir)
            print(f"  Created attempt: {attempt_path}")

            # Commit the plan
            git_commit_and_push(
                repo_root,
                f"goal-agent: plan attempt for [{task.goal_name}] {task.description}",
            )

            # Execute via Claude API
            remaining = MAX_BUDGET_USD - cumulative_cost
            result = execute_task(task_dict, remaining_budget=remaining)
            task_cost = result.get("cost_usd", 0.0)
            cumulative_cost += task_cost
            print(f"  Tokens used: {result['tokens_used']}")
            print(f"  Task cost: ${task_cost:.4f} | Cumulative: ${cumulative_cost:.4f} / ${MAX_BUDGET_USD:.2f}")

            if result["needs_clarification"]:
                # Blocked — needs user input
                print(f"  BLOCKED — needs clarification")
                update_attempt_with_results(attempt_path, result, status="blocked")
                ask_clarification(task_dict, result["clarification_question"] or "See attempt file for details.")
                stats["blocked"] += 1

            else:
                # Success — save results
                update_attempt_with_results(attempt_path, result, status="completed")
                save_result_files(task.goal_dir, task_dict, result)

                # Check off the task in the goal index
                checked = check_off_task(task.goal_index_path, task.description)
                if checked:
                    print(f"  Checked off task in goal index")
                    update_goal_status(task.goal_index_path)

                # Extract summary for notification
                summary_lines = result["result"].split("\n")
                summary = next(
                    (l for l in summary_lines if l.strip() and not l.startswith("#")),
                    "Task completed successfully.",
                )
                notify_task_completed(task_dict, summary)
                stats["completed"] += 1

            # Commit results
            git_commit_and_push(
                repo_root,
                f"goal-agent: results for [{task.goal_name}] {task.description}",
            )

        except BudgetExceededException as e:
            print(f"  BUDGET EXCEEDED: {e}")
            notify_task_failed(task_dict, f"Budget exceeded: {e}")
            stats["failed"] += 1
            
            # Commit partial results and break
            git_commit_and_push(
                repo_root,
                f"goal-agent: budget exceeded at [{task.goal_name}] {task.description}",
            )
            break

        except Exception as e:
            print(f"  FAILED: {e}")
            traceback.print_exc()
            notify_task_failed(task_dict, str(e))
            stats["failed"] += 1

            # Try to commit any partial results
            git_commit_and_push(
                repo_root,
                f"goal-agent: failed attempt for [{task.goal_name}] {task.description}",
            )

    # Step 4: Run summary
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
    
    # Exit with error if budget was exceeded
    if cumulative_cost > MAX_BUDGET_USD:
        print(f"ERROR: Budget exceeded (${cumulative_cost:.4f} > ${MAX_BUDGET_USD:.2f})")
        sys.exit(1)
