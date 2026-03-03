"""
Goal Executor — takes a task from the work queue, calls MiniMax API
(Anthropic-compatible) to execute it with tool support, and returns the results.
"""

import os
import anthropic
from pathlib import Path
from rate_limiter import limiter
from budget import check_budget_before_call
from tools import TOOL_DEFINITIONS, execute_tool

MINIMAX_BASE_URL = "https://api.minimax.io/anthropic"
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")

MODEL = os.environ.get("GOAL_AGENT_MODEL", "MiniMax-M2.5")
MAX_TOKENS = int(os.environ.get("GOAL_AGENT_MAX_TOKENS", "8192"))
MAX_TOOL_ROUNDS = int(os.environ.get("GOAL_AGENT_MAX_TOOL_ROUNDS", "15"))

COST_PER_MTOK = {
    "MiniMax-M2.5": {"input": 0.30, "output": 1.10},
    "MiniMax-M2.5-highspeed": {"input": 0.30, "output": 1.10},
    "MiniMax-M2.1": {"input": 0.30, "output": 1.10},
}
DEFAULT_COST = {"input": 0.30, "output": 1.10}


def estimate_cost(input_tokens: int, output_tokens: int, model: str = MODEL) -> float:
    """Estimate USD cost from token counts."""
    rates = COST_PER_MTOK.get(model, DEFAULT_COST)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000

SYSTEM_PROMPT = """You are an autonomous goal execution agent working on tasks from a personal vision board.

## Your Role
You execute specific tasks from a goal. Each task is a concrete action item. Your job is to:
1. Understand what the task requires
2. Research and reason about the best approach
3. Return thorough, actionable results

## Guidelines
- Be thorough and analytical.
- Provide specific, actionable information — not vague summaries.
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


def build_task_prompt(task: dict, goal_context: str, user_answer: str | None = None) -> str:
    """Build the user message prompt from the task and goal context."""
    prompt = f"""## Task to Execute

**Goal:** {task['goal_title']}
**Task:** {task['description']}
**Deadline:** {task.get('deadline', 'None')}

## Goal Context

{goal_context}

## Instructions

Execute this task thoroughly.
Produce a complete deliverable that can be saved as a file in the goal folder.
"""

    if user_answer:
        prompt += f"""
## User's Clarification Response

You previously asked for clarification on this task. The user has provided the following answer:

{user_answer}

Use this information to complete the task. Do NOT ask for further clarification on the same topic.
"""

    return prompt


def load_goal_context(goal_index_path: str) -> str:
    """Read the goal's index.md to provide context to the agent."""
    try:
        return Path(goal_index_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return "(Goal context file not found)"


def _extract_text(content_blocks) -> str:
    """Extract concatenated text from a list of content blocks."""
    return "".join(block.text for block in content_blocks if block.type == "text")


def _extract_tool_uses(content_blocks) -> list:
    """Extract tool_use blocks from a response."""
    return [block for block in content_blocks if block.type == "tool_use"]


def execute_task(
    task: dict,
    remaining_budget: float | None = None,
    user_answer: str | None = None,
) -> dict:
    """
    Execute a single task using the MiniMax API with an agentic tool-use loop.

    The model can call web_search and web_fetch tools. Each tool call triggers
    another API round until the model produces a final text response or we hit
    MAX_TOOL_ROUNDS.

    Args:
        task: Task dict with description, goal_name, goal_title, etc.
        remaining_budget: Budget remaining in USD (None = unlimited).
        user_answer: If provided, injects the user's clarification answer into the prompt.

    Returns a dict with:
        - result: the markdown output from the agent
        - needs_clarification: bool
        - clarification_question: str or None
        - tokens_used: dict with input/output counts (accumulated across rounds)
        - model: which model was used
        - cost_usd: estimated cost of this task
        - tool_calls_made: number of tool calls executed
    """
    if remaining_budget is not None:
        estimated_cost = 0.10
        if not check_budget_before_call(remaining_budget, estimated_cost):
            print(f"  Budget insufficient (${remaining_budget:.4f} remaining) — skipping task")
            return {
                "result": "",
                "needs_clarification": False,
                "clarification_question": None,
                "tokens_used": {"input": 0, "output": 0},
                "cost_usd": 0.0,
                "model": MODEL,
                "budget_exceeded": True,
                "tool_calls_made": 0,
            }

    client = anthropic.Anthropic(
        base_url=MINIMAX_BASE_URL,
        api_key=MINIMAX_API_KEY,
    )

    goal_context = load_goal_context(task["goal_index_path"])
    user_prompt = build_task_prompt(task, goal_context, user_answer=user_answer)

    messages = [{"role": "user", "content": user_prompt}]
    total_input_tokens = 0
    total_output_tokens = 0
    total_tool_calls = 0

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        limiter.wait_if_needed()
        print(f"  Round {round_num}/{MAX_TOOL_ROUNDS} | Rate limiter: {limiter.status()}")

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        limiter.record_call(
            tokens_used=response.usage.input_tokens + response.usage.output_tokens
        )

        tool_uses = _extract_tool_uses(response.content)

        if response.stop_reason != "tool_use" or not tool_uses:
            break

        # Execute each tool call and build results
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tool_use in tool_uses:
            total_tool_calls += 1
            result_str = execute_tool(tool_use.name, tool_use.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})
        print(f"  Executed {len(tool_uses)} tool call(s), continuing...")

    result_text = _extract_text(response.content)
    cost = estimate_cost(total_input_tokens, total_output_tokens)

    print(f"  Finished after {round_num} round(s), {total_tool_calls} tool call(s)")

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

    return {
        "result": result_text,
        "needs_clarification": needs_clarification,
        "clarification_question": clarification_question,
        "tokens_used": {"input": total_input_tokens, "output": total_output_tokens},
        "cost_usd": cost,
        "model": MODEL,
        "budget_exceeded": False,
        "tool_calls_made": total_tool_calls,
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
