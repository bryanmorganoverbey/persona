"""
Telegram Notifier — sends status updates and clarification questions
to the user via Telegram Bot API, and polls for replies.
"""

import os
import requests


TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


def _configured() -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured — skipping")
        return False
    return True


def send_message(text: str, parse_mode: str = "Markdown") -> int | None:
    """Send a message via Telegram. Returns the message_id on success, None on failure."""
    if not _configured():
        print(f"Would have sent: {text[:200]}...")
        return None

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
        data = resp.json()
        return data.get("result", {}).get("message_id")
    except requests.RequestException:
        # Retry without parse_mode in case of formatting issues
        try:
            resp = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("result", {}).get("message_id")
        except requests.RequestException as e:
            print(f"Telegram send failed: {e}")
            return None


def get_replies_since(since_message_id: int) -> list[str]:
    """
    Poll Telegram getUpdates for messages from the user in our chat
    that arrived after since_message_id.

    Returns a list of message texts in chronological order.
    """
    if not _configured():
        return []

    try:
        resp = requests.post(
            f"{TELEGRAM_API}/getUpdates",
            json={"timeout": 5, "allowed_updates": ["message"]},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"Telegram getUpdates failed: {e}")
        return []

    replies = []
    chat_id_str = str(TELEGRAM_CHAT_ID)

    for update in data.get("result", []):
        msg = update.get("message", {})
        msg_chat_id = str(msg.get("chat", {}).get("id", ""))
        msg_id = msg.get("message_id", 0)
        text = msg.get("text", "")

        if msg_chat_id != chat_id_str:
            continue
        if msg_id <= since_message_id:
            continue
        if msg.get("from", {}).get("is_bot", False):
            continue
        if text.strip():
            replies.append(text)

    return replies


def notify_task_started(task: dict) -> int | None:
    """Notify that the agent has started working on a task."""
    text = (
        f"*Goal Agent — Task Started*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n"
        f"*Deadline:* {task.get('deadline', 'None')}"
    )
    return send_message(text)


def notify_task_completed(task: dict, summary: str) -> int | None:
    """Notify that a task was completed successfully."""
    text = (
        f"*Goal Agent — Task Completed*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n\n"
        f"*Summary:* {summary[:500]}"
    )
    return send_message(text)


def notify_task_failed(task: dict, reason: str) -> int | None:
    """Notify that a task failed."""
    text = (
        f"*Goal Agent — Task Failed*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n\n"
        f"*Reason:* {reason[:500]}"
    )
    return send_message(text)


def ask_clarification(task: dict, question: str) -> int | None:
    """Send a clarification question to the user. Returns the message_id for reply tracking."""
    text = (
        f"*Goal Agent — Needs Your Input*\n\n"
        f"*Goal:* {task['goal_title']}\n"
        f"*Task:* {task['description']}\n\n"
        f"*Question:*\n{question[:1000]}\n\n"
        f"_Reply to this message with your answer and the agent will use it on the next run._"
    )
    return send_message(text)


def notify_run_summary(attempted: int, completed: int, failed: int, blocked: int) -> int | None:
    """Send a summary of the entire run."""
    text = (
        f"*Goal Agent — Run Complete*\n\n"
        f"Attempted: {attempted}\n"
        f"Completed: {completed}\n"
        f"Failed: {failed}\n"
        f"Blocked (need input): {blocked}"
    )
    return send_message(text)
