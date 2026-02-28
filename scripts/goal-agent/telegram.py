"""
Telegram Notifier — sends status updates and clarification questions
to the user via Telegram Bot API.
"""

import os
import requests


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message via Telegram. Returns True on success."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured — skipping notification")
        print(f"Would have sent: {text[:200]}...")
        return False

    # Telegram has a 4096 char limit per message
    if len(text) > 4000:
        text = text[:3950] + "\n\n_(truncated)_"

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": parse_mode,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"Telegram send failed: {e}")
        # Retry without parse_mode in case of formatting issues
        try:
            resp = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException:
            return False


def notify_task_started(task: dict) -> bool:
    """Notify that the agent has started working on a task."""
    text = (
        f"*Goal Agent — Task Started*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n"
        f"*Deadline:* {task.get('deadline', 'None')}"
    )
    return send_message(text)


def notify_task_completed(task: dict, summary: str) -> bool:
    """Notify that a task was completed successfully."""
    text = (
        f"*Goal Agent — Task Completed*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n\n"
        f"*Summary:* {summary[:500]}"
    )
    return send_message(text)


def notify_task_failed(task: dict, reason: str) -> bool:
    """Notify that a task failed."""
    text = (
        f"*Goal Agent — Task Failed*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n\n"
        f"*Reason:* {reason[:500]}"
    )
    return send_message(text)


def ask_clarification(task: dict, question: str) -> bool:
    """Send a clarification question to the user."""
    text = (
        f"*Goal Agent — Needs Your Input*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n\n"
        f"*Question:*\n{question[:1000]}\n\n"
        f"_Add your answer to the goal folder and the agent will pick it up on the next run._"
    )
    return send_message(text)


def notify_run_summary(attempted: int, completed: int, failed: int, blocked: int) -> bool:
    """Send a summary of the entire run."""
    text = (
        f"*Goal Agent — Run Complete*\n\n"
        f"Attempted: {attempted}\n"
        f"Completed: {completed}\n"
        f"Failed: {failed}\n"
        f"Blocked (need input): {blocked}"
    )
    return send_message(text)
