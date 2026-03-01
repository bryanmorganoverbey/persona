"""
Persona Questionnaire Agent — main orchestrator.

State machine with two modes:
  1. REPLY MODE  — pending questions exist; poll Telegram for answers,
                   integrate them into category files, commit, clear state.
  2. QUESTION MODE — no pending questions; scan categories, generate new
                     questions, send via Telegram, save state.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from scanner import scan_categories, build_category_summary
from generator import generate_questions
from budget import BudgetExceededException
from integrator import (
    parse_numbered_replies,
    match_answers_to_questions,
    generate_file_updates,
    apply_operations,
    update_index_files_table,
    git_commit_and_push,
)
from telegram import get_replies_since, send_questions, send_status

MAX_BUDGET_USD = float(os.environ.get("QUESTIONNAIRE_MAX_BUDGET_USD", "2.0"))
STALE_HOURS = int(os.environ.get("QUESTIONNAIRE_STALE_HOURS", "24"))


def state_path(repo_root: str) -> Path:
    return Path(repo_root) / "scripts" / "persona-questionnaire" / "state.json"


def load_state(repo_root: str) -> dict | None:
    sp = state_path(repo_root)
    if not sp.exists():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_state(repo_root: str, state: dict) -> None:
    sp = state_path(repo_root)
    sp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def clear_state(repo_root: str) -> None:
    sp = state_path(repo_root)
    if sp.exists():
        sp.unlink()


def is_stale(state: dict) -> bool:
    """Check if pending questions have been waiting too long without a reply."""
    sent_at = state.get("sent_at", "")
    if not sent_at:
        return False
    try:
        sent_time = datetime.fromisoformat(sent_at)
        elapsed = (datetime.now(timezone.utc) - sent_time).total_seconds() / 3600
        return elapsed > STALE_HOURS
    except (ValueError, TypeError):
        return False


def load_question_history(repo_root: str) -> list[str]:
    """Load previously asked questions to avoid repetition."""
    history_path = Path(repo_root) / "scripts" / "persona-questionnaire" / "history.json"
    if not history_path.exists():
        return []
    try:
        return json.loads(history_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_question_history(repo_root: str, questions: list[str]) -> None:
    history_path = Path(repo_root) / "scripts" / "persona-questionnaire" / "history.json"
    # Keep last 200 questions
    trimmed = questions[-200:]
    history_path.write_text(json.dumps(trimmed, indent=2) + "\n", encoding="utf-8")


def read_profile(repo_root: str) -> str:
    profile_path = Path(repo_root) / "profile.md"
    try:
        return profile_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "(profile.md not found)"


def run_generate_toc(repo_root: str) -> None:
    """Run generate-toc.sh if new categories were created."""
    toc_script = Path(repo_root) / "scripts" / "generate-toc.sh"
    if toc_script.exists():
        try:
            subprocess.run(
                ["bash", str(toc_script), "--write"],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )
            print("  Updated README.md table of contents")
        except subprocess.CalledProcessError as e:
            print(f"  generate-toc.sh failed: {e}")


def handle_replies(repo_root: str, state: dict, remaining_budget: float) -> dict:
    """
    Poll for replies, integrate answers, commit changes.
    
    Args:
        repo_root: Repository root directory
        state: Current state with pending questions
        remaining_budget: Remaining budget in USD
        
    Returns stats dict.
    """
    stats = {"answers_received": 0, "files_modified": 0, "cost_usd": 0.0}

    message_id = state.get("message_id")
    questions = state.get("questions", [])

    if not message_id or not questions:
        print("Invalid state — clearing and starting fresh")
        clear_state(repo_root)
        return stats

    print(f"Checking for replies to message {message_id}...")
    replies = get_replies_since(message_id)

    if not replies:
        if is_stale(state):
            print("Questions are stale — clearing state and generating fresh ones")
            send_status("No replies received in 24h — sending fresh questions.")
            clear_state(repo_root)
        else:
            print("No replies yet — waiting")
        return stats

    print(f"Found {len(replies)} reply message(s)")

    # Parse numbered answers
    answers = parse_numbered_replies(replies)
    print(f"Parsed {len(answers)} numbered answers")
    stats["answers_received"] = len(answers)

    if not answers:
        print("No numbered answers found in replies — waiting for properly formatted replies")
        return stats

    # Match to questions
    matched = match_answers_to_questions(questions, answers)
    print(f"Matched {len(matched)} answers to questions")

    if not matched:
        print("No answers matched to questions")
        clear_state(repo_root)
        return stats

    # Generate file updates via Claude
    print("Generating file updates from answers...")
    operations, cost = generate_file_updates(matched, repo_root, remaining_budget=remaining_budget)
    stats["cost_usd"] += cost
    print(f"  Generated {len(operations)} file operations (cost: ${cost:.4f})")

    if operations:
        modified = apply_operations(operations, repo_root)
        stats["files_modified"] = len(modified)

        # Update index.md files tables for affected categories
        affected_cats = set()
        for fpath in modified:
            parts = Path(fpath).relative_to(repo_root).parts
            if len(parts) >= 2:
                cat_dir = str(Path(repo_root) / parts[0])
                affected_cats.add(cat_dir)

        for cat_dir in affected_cats:
            cat_modified = [f for f in modified if f.startswith(cat_dir)]
            update_index_files_table(cat_dir, cat_modified)

        # Check if any new categories were created
        new_cat_ops = [op for op in operations if op.get("operation") == "create" and op.get("path", "").endswith("index.md")]
        if new_cat_ops:
            run_generate_toc(repo_root)

        # Commit
        n_answers = len(matched)
        git_commit_and_push(
            repo_root,
            f"persona-questionnaire: integrate {n_answers} answers into profile",
        )

        send_status(
            f"Integrated {n_answers} answers into {len(modified)} files."
        )

    clear_state(repo_root)
    return stats


def handle_questions(repo_root: str, remaining_budget: float) -> dict:
    """
    Scan categories, generate questions, send via Telegram, save state.
    
    Args:
        repo_root: Repository root directory
        remaining_budget: Remaining budget in USD
        
    Returns stats dict.
    """
    stats = {"questions_sent": 0, "cost_usd": 0.0}

    # Scan categories
    print("Scanning persona categories...")
    categories = scan_categories(repo_root)
    summary = build_category_summary(categories)
    print(f"Found {len(categories)} categories")

    sparse = [c for c in categories if c.is_sparse]
    print(f"Sparse categories: {len(sparse)}")

    # Read profile for context
    profile = read_profile(repo_root)

    # Load history to avoid repeats
    history = load_question_history(repo_root)

    # Generate questions
    print("Generating questions via Claude...")
    questions, cost = generate_questions(summary, profile, history, remaining_budget=remaining_budget)
    stats["cost_usd"] += cost
    print(f"Generated {len(questions)} questions (cost: ${cost:.4f})")

    if not questions:
        print("No questions generated — nothing to send")
        return stats

    # Send via Telegram
    print("Sending questions via Telegram...")
    message_id = send_questions(questions)

    if message_id:
        print(f"Sent questions (message_id: {message_id})")
        stats["questions_sent"] = len(questions)

        # Save state
        save_state(repo_root, {
            "message_id": message_id,
            "questions": questions,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })

        # Update history
        new_texts = [q["text"] for q in questions]
        history.extend(new_texts)
        save_question_history(repo_root, history)

        # Commit state + history
        git_commit_and_push(
            repo_root,
            "persona-questionnaire: sent new batch of questions",
        )
    else:
        print("Failed to send questions via Telegram")

    return stats


def run(repo_root: str) -> dict:
    """
    Main execution loop.

    1. Check for pending questions (reply mode)
    2. If none pending, generate and send new questions (question mode)
    """
    print(f"=== Persona Questionnaire Run: {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Repo root: {repo_root}")
    print(f"Budget limit: ${MAX_BUDGET_USD:.2f}")

    cumulative_cost = 0.0
    stats = {
        "mode": "",
        "answers_received": 0,
        "files_modified": 0,
        "questions_sent": 0,
        "cost_usd": 0.0,
    }

    # Check for pending state
    state = load_state(repo_root)

    try:
        if state:
            print(f"\nPending questions found (sent at {state.get('sent_at', 'unknown')})")
            stats["mode"] = "reply"
            remaining = MAX_BUDGET_USD - cumulative_cost
            reply_stats = handle_replies(repo_root, state, remaining_budget=remaining)
            cumulative_cost += reply_stats.get("cost_usd", 0.0)
            stats["answers_received"] = reply_stats.get("answers_received", 0)
            stats["files_modified"] = reply_stats.get("files_modified", 0)

            # If we processed replies (state was cleared), also send new questions
            # unless we're over budget
            refreshed_state = load_state(repo_root)
            if refreshed_state is None and cumulative_cost < MAX_BUDGET_USD:
                print("\nState cleared — generating new questions...")
                remaining = MAX_BUDGET_USD - cumulative_cost
                q_stats = handle_questions(repo_root, remaining_budget=remaining)
                cumulative_cost += q_stats.get("cost_usd", 0.0)
                stats["questions_sent"] = q_stats.get("questions_sent", 0)
        else:
            print("\nNo pending questions — generating new batch")
            stats["mode"] = "question"
            remaining = MAX_BUDGET_USD - cumulative_cost
            q_stats = handle_questions(repo_root, remaining_budget=remaining)
            cumulative_cost += q_stats.get("cost_usd", 0.0)
            stats["questions_sent"] = q_stats.get("questions_sent", 0)

    except BudgetExceededException as e:
        print(f"\nBUDGET EXCEEDED: {e}")
        send_status(f"Budget exceeded: {e}")
        stats["cost_usd"] = cumulative_cost
        print(f"\n=== Run Terminated (Budget Exceeded) ===")
        print(f"Total cost: ${cumulative_cost:.4f} / ${MAX_BUDGET_USD:.2f}")
        print(f"ERROR: Budget exceeded")
        sys.exit(1)

    stats["cost_usd"] = cumulative_cost

    print(f"\n=== Run Complete ===")
    print(f"Mode: {stats['mode']}")
    print(f"Answers received: {stats['answers_received']}")
    print(f"Files modified: {stats['files_modified']}")
    print(f"Questions sent: {stats['questions_sent']}")
    print(f"Total cost: ${cumulative_cost:.4f}")

    return stats


if __name__ == "__main__":
    repo_root = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    stats = run(repo_root)

    if stats["questions_sent"] == 0 and stats["answers_received"] == 0:
        print("Nothing happened this run (waiting for replies or no questions generated)")
