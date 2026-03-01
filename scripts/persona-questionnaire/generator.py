"""
Question Generator — uses Claude to produce persona questions,
split between enriching existing categories and suggesting new ones.
"""

import json
import os

import anthropic

from rate_limiter import limiter
from budget import check_budget_before_call

MODEL = os.environ.get("QUESTIONNAIRE_MODEL", "claude-sonnet-4-6")
NUM_QUESTIONS = int(os.environ.get("QUESTIONNAIRE_NUM_QUESTIONS", "5"))
MAX_TOKENS = 4096

COST_PER_MTOK = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
}
DEFAULT_COST = {"input": 3.0, "output": 15.0}


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_MTOK.get(MODEL, DEFAULT_COST)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


SYSTEM_PROMPT = """You are a persona-building assistant. Your job is to generate thoughtful,
specific questions that help build a detailed personal preference profile.

You will receive a summary of existing persona categories and their current depth.
The user will tell you exactly how many questions to generate, split between two groups:

1. ENRICH questions: Questions that add depth to existing categories, especially
   sparse ones. Target specific gaps — don't ask about things already well-documented.
   Focus on actionable preferences that an AI agent could use.

2. NEW CATEGORY questions: Suggest new categories that aren't covered yet,
   framed as questions. For example, if there's no "hobbies" category, ask about
   hobbies and interests.

## Output Format

Return ONLY a JSON array. Each element:
{
  "number": 1,
  "text": "The question text",
  "category": "existing-category-name or suggested-new-category",
  "type": "enrich" or "new",
  "target_file": "suggested filename for the answer, e.g. morning-routine.md"
}

## Question Quality Guidelines

- Be SPECIFIC, not generic. "What's your go-to order at a coffee shop?" not "Tell me about beverages."
- Ask about actionable preferences an AI could use to help.
- Vary the style: some multiple choice, some open-ended, some "rank these."
- Don't re-ask things already covered in existing files.
- Questions should feel conversational, like a friend getting to know you better.
- Each question should stand alone — don't reference other questions.
"""


def generate_questions(
    category_summary: str,
    profile_text: str,
    previous_questions: list[str] | None = None,
    remaining_budget: float | None = None,
) -> tuple[list[dict], float]:
    """
    Generate persona questions using Claude.

    Args:
        category_summary: Summary of existing categories
        profile_text: User profile content
        previous_questions: List of previously asked questions to avoid
        remaining_budget: Remaining budget in USD. If provided, will check before API call.

    Returns (questions_list, cost_usd).
    """
    # Check budget before making API call
    if remaining_budget is not None:
        # Estimate: ~4K tokens at Sonnet-4-6 rates = ~$0.06 typical
        estimated_cost = 0.06
        if not check_budget_before_call(remaining_budget, estimated_cost):
            print(
                f"  Budget insufficient (${remaining_budget:.4f} remaining, ${estimated_cost:.2f} needed) - skipping question generation"
            )
            return [], 0.0

    client = anthropic.Anthropic()

    n_new = max(1, round(NUM_QUESTIONS * 0.4))
    n_enrich = NUM_QUESTIONS - n_new

    previous_note = ""
    if previous_questions:
        recent = previous_questions[-40:]
        previous_note = (
            "\n\n## Previously Asked Questions (avoid repeating)\n\n"
            + "\n".join(f"- {q}" for q in recent)
        )

    user_prompt = f"""## Current Profile Summary

{profile_text}

## Category Inventory

{category_summary}
{previous_note}

## Instructions

Generate exactly {NUM_QUESTIONS} questions: {n_enrich} to enrich existing categories (prioritize sparse ones)
and {n_new} suggesting new categories. Return as a JSON array.
"""

    limiter.wait_if_needed()

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    total_tokens = response.usage.input_tokens + response.usage.output_tokens
    limiter.record_call(tokens_used=total_tokens)
    cost = estimate_cost(response.usage.input_tokens, response.usage.output_tokens)

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    # Parse JSON from the response, handling markdown code fences
    cleaned = result_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]  # remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    try:
        questions = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Failed to parse questions JSON: {e}")
        print(f"Raw response:\n{result_text[:500]}")
        questions = []

    # Ensure numbering is sequential
    for i, q in enumerate(questions, 1):
        q["number"] = i

    return questions, cost
