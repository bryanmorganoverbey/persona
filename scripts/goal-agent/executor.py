"""
Goal Executor — takes a task from the work queue, calls Claude API with tools
to execute it, and returns the results.
"""

import os
import anthropic
from pathlib import Path
from rate_limiter import limiter


MODEL = os.environ.get("GOAL_AGENT_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = int(os.environ.get("GOAL_AGENT_MAX_TOKENS", "8192"))

COST_PER_MTOK = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
}
DEFAULT_COST = {"input": 3.0, "output": 15.0}


def estimate_cost(input_tokens: int, output_tokens: int, model: str = MODEL) -> float:
    """Estimate USD cost from token counts."""
    rates = COST_PER_MTOK.get(model, DEFAULT_COST)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

SYSTEM_PROMPT = """You are an autonomous goal execution agent working on tasks from a personal vision board.

## Your Role
You execute specific tasks from a goal. Each task is a concrete action item. Your job is to:
1. Understand what the task requires
2. Use web search, web fetch, and code execution tools to accomplish it
3. Return thorough, actionable results

## Guidelines
- Be thorough in your research. Use multiple sources when possible.
- Provide specific, actionable information — not vague summaries.
- Include links to sources when you find useful information.
- If the task requires creating a deliverable (list, comparison, analysis), produce the full deliverable.
- If you cannot complete the task fully, explain exactly what you accomplished and what remains.
- If you need information from the user to proceed, clearly state what you need in a section called "CLARIFICATION NEEDED".

## Output Format
Structure your response as markdown with clear sections:
- ## Summary — one paragraph of what you did
- ## Findings / Results — the detailed output
- ## Sources — links used
- ## Next Steps — what should happen next (if anything)
- ## CLARIFICATION NEEDED — only if you're blocked and need user input

## Context
You are working within a persona repository that tracks personal goals, preferences, and vision boards.
The user is a software engineer and digital nomad currently in Mexico, planning to move to Tennessee.
"""


def build_task_prompt(task: dict, goal_context: str) -> str:
    """Build the user message prompt from the task and goal context."""
    prompt = f"""## Task to Execute

**Goal:** {task['goal_title']}
**Task:** {task['description']}
**Deadline:** {task.get('deadline', 'None')}

## Goal Context

{goal_context}

## Instructions

Execute this task thoroughly. Use web search to find real, current information.
Produce a complete deliverable that can be saved as a file in the goal folder.
"""
    return prompt


def load_goal_context(goal_index_path: str) -> str:
    """Read the goal's index.md to provide context to the agent."""
    try:
        return Path(goal_index_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "(Goal context file not found)"


def execute_task(task: dict) -> dict:
    """
    Execute a single task using the Claude API with tool use.

    Returns a dict with:
        - result: the markdown output from the agent
        - needs_clarification: bool
        - clarification_question: str or None
        - tokens_used: dict with input/output counts
        - model: which model was used
    """
    client = anthropic.Anthropic()

    goal_context = load_goal_context(task["goal_index_path"])
    user_prompt = build_task_prompt(task, goal_context)

    limiter.wait_if_needed()
    print(f"  Rate limiter: {limiter.status()}")

    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        tools=[
            {"type": "web_search_20260209", "name": "web_search"},
            {"type": "web_fetch_20260209", "name": "web_fetch"},
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    total_tokens = response.usage.input_tokens + response.usage.output_tokens
    limiter.record_call(tokens_used=total_tokens)

    # Extract text blocks from the response
    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text += block.text

    needs_clarification = "CLARIFICATION NEEDED" in result_text
    clarification_question = None
    if needs_clarification:
        import re
        match = re.search(
            r"## CLARIFICATION NEEDED\s*\n+(.*?)(?=\n## |\Z)",
            result_text,
            re.DOTALL,
        )
        if match:
            clarification_question = match.group(1).strip()

    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens
    cost = estimate_cost(input_tok, output_tok)

    return {
        "result": result_text,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "tokens_used": {"input": input_tok, "output": output_tok},
        "cost_usd": cost,
        "model": MODEL,
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python executor.py '<task_json>'")
        sys.exit(1)

    task = json.loads(sys.argv[1])
    print(f"Executing task: {task['description']}")
    print(f"Goal: {task['goal_title']}")
    print(f"Model: {MODEL}")
    print("---")

    result = execute_task(task)

    print(result["result"])
    print("---")
    print(f"Tokens: {result['tokens_used']}")
    print(f"Needs clarification: {result['needs_clarification']}")
