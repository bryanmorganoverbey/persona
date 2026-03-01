"""
Telegram Client — sends questionnaire messages and polls for user replies.

Uses getUpdates (long-polling) to retrieve replies, which works well for
periodic GitHub Actions runs without requiring a webhook server.
"""

import json
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
    """
    Send a message via Telegram.
    Returns the message_id on success, None on failure.
    """
    if not _configured():
        print(f"Would have sent:\n{text[:300]}...")
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
            timeout=15,
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
                timeout=15,
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

        # Only messages in our chat, after the questions message, from a user (not bot)
        if msg_chat_id != chat_id_str:
            continue
        if msg_id <= since_message_id:
            continue
        if msg.get("from", {}).get("is_bot", False):
            continue
        if text.strip():
            replies.append(text)

    return replies


def send_questions(questions: list[dict]) -> int | None:
    """
    Send a numbered list of questions as a single Telegram message.
    Each question dict has: number, text, category, type (enrich/new).
    Returns the message_id.
    """
    lines = ["*Persona Questionnaire*\n"]
    lines.append("Reply with numbered answers (e.g. 1. Your answer here).\n")
    lines.append("Skip any you don't want to answer by leaving them out.\n")

    current_section = None
    for q in questions:
        section = "Enriching Existing Categories" if q["type"] == "enrich" else "New Category Suggestions"
        if section != current_section:
            lines.append(f"\n*{section}:*\n")
            current_section = section

        cat_label = f" [{q['category']}]" if q.get("category") else ""
        lines.append(f"{q['number']}. {q['text']}{cat_label}")

    text = "\n".join(lines)
    return send_message(text)


def send_status(text: str) -> int | None:
    """Send a status/notification message."""
    return send_message(f"*Persona Questionnaire Agent*\n\n{text}")
