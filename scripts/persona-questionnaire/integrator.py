"""
Answer Integrator — takes user replies, matches them to questions, and uses
Claude to merge answers into the appropriate category files.
"""

import json
import os
import re
import subprocess
from datetime import date
from pathlib import Path

import anthropic

from rate_limiter import limiter
from budget import check_budget_before_call, BudgetExceededException

MODEL = os.environ.get("QUESTIONNAIRE_MODEL", "claude-sonnet-4-6")
MAX_TOKENS = 4096

COST_PER_MTOK = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
}
DEFAULT_COST = {"input": 3.0, "output": 15.0}


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    rates = COST_PER_MTOK.get(MODEL, DEFAULT_COST)
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


SYSTEM_PROMPT = """You are a persona-profile editor. Given a user's answers to persona questions,
produce file updates to integrate those answers into their preference repository.

## Repository Structure

Each category is a top-level folder with:
- index.md — category overview, related categories, file listing
- topic-specific .md files with frontmatter (last_reviewed, confidence) and content

## Rules

- Match the writing style of existing files: concise, direct, casual tone.
- Use markdown with clear headings and bullet points.
- Include an "Agent Guidelines" section where appropriate.
- Add YAML frontmatter (last_reviewed, confidence) to new files.
- For existing files, append or update sections — don't rewrite unrelated content.
- For new categories, create the index.md following the standard template.

## Output Format

Return ONLY a JSON array of file operations:
[
  {
    "operation": "create" | "append" | "update",
    "path": "category/filename.md",
    "content": "full file content for create, or section to append/update",
    "description": "brief description of what this adds"
  }
]

For "update" operations, include a "find" field with the text to replace and
"content" as the replacement text.

For "append" operations, "content" is appended to the end of the file.

For "create" operations, "content" is the full file content.
"""


def parse_numbered_replies(reply_texts: list[str]) -> dict[int, str]:
    """
    Parse numbered answers from user reply messages.
    Handles formats like "1. answer", "1) answer", "1: answer".
    Multiple answers can be in a single message.
    """
    answers = {}

    for text in reply_texts:
        # Split on numbered patterns at the start of lines
        parts = re.split(r"(?:^|\n)\s*(\d+)\s*[.):\-]\s*", text)

        # parts alternates: [preamble, number, answer, number, answer, ...]
        i = 1
        while i + 1 < len(parts):
            num = int(parts[i])
            answer = parts[i + 1].strip()
            if answer:
                # If same number appears multiple times, concat
                if num in answers:
                    answers[num] += " " + answer
                else:
                    answers[num] = answer
            i += 2

    return answers


def match_answers_to_questions(
    questions: list[dict], answers: dict[int, str]
) -> list[dict]:
    """Match parsed answers to their original questions."""
    matched = []
    for q in questions:
        num = q["number"]
        if num in answers:
            matched.append({**q, "answer": answers[num]})
    return matched


def generate_file_updates(
    matched_qa: list[dict], repo_root: str, remaining_budget: float | None = None
) -> tuple[list[dict], float]:
    """
    Use Claude to generate file operations from matched Q&A pairs.
    
    Args:
        matched_qa: List of matched question-answer pairs
        repo_root: Root directory of the repository
        remaining_budget: Remaining budget in USD. If provided, will check before API call.
    
    Returns (operations_list, cost_usd).
    """
    if not matched_qa:
        return [], 0.0

    # Check budget before making API call
    if remaining_budget is not None:
        # Estimate: ~4K tokens at Sonnet-4-6 rates = ~$0.06 typical
        estimated_cost = 0.06
        if not check_budget_before_call(remaining_budget, estimated_cost):
            print(f"  Budget insufficient (${remaining_budget:.4f} < ${estimated_cost:.2f}) - skipping file update generation")
            return [], 0.0

    client = anthropic.Anthropic()

    # Read existing file contents for context
    existing_context = []
    seen_categories = set()
    for qa in matched_qa:
        cat = qa.get("category", "")
        if cat and cat not in seen_categories:
            seen_categories.add(cat)
            cat_dir = Path(repo_root) / cat
            if cat_dir.exists():
                for md in sorted(cat_dir.rglob("*.md")):
                    try:
                        content = md.read_text(encoding="utf-8")
                        rel = md.relative_to(repo_root)
                        existing_context.append(f"### {rel}\n```\n{content}\n```")
                    except (OSError, UnicodeDecodeError):
                        pass

    qa_text = "\n\n".join(
        f"**Q{qa['number']}** [{qa.get('category', 'new')}] ({qa['type']}): "
        f"{qa['text']}\n**A:** {qa['answer']}"
        for qa in matched_qa
    )

    existing_text = "\n\n".join(existing_context[:20])  # cap context size

    user_prompt = f"""## Answered Questions

{qa_text}

## Existing Files (for context)

{existing_text}

## Instructions

Generate file operations to integrate these answers into the persona repository.
Today's date is {date.today().isoformat()}.
Return as a JSON array of operations.
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

    # Parse JSON
    cleaned = result_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    try:
        operations = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Failed to parse operations JSON: {e}")
        print(f"Raw response:\n{result_text[:500]}")
        operations = []

    return operations, cost


def apply_operations(operations: list[dict], repo_root: str) -> list[str]:
    """
    Apply file operations to the repo. Returns list of modified file paths.
    """
    modified = []
    root = Path(repo_root)

    for op in operations:
        rel_path = op.get("path", "")
        if not rel_path:
            continue

        filepath = root / rel_path
        operation = op.get("operation", "create")

        try:
            if operation == "create":
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_text(op["content"], encoding="utf-8")
                print(f"  Created: {rel_path}")
                modified.append(str(filepath))

            elif operation == "append":
                if filepath.exists():
                    existing = filepath.read_text(encoding="utf-8")
                    filepath.write_text(
                        existing.rstrip() + "\n\n" + op["content"] + "\n",
                        encoding="utf-8",
                    )
                else:
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(op["content"] + "\n", encoding="utf-8")
                print(f"  Appended: {rel_path}")
                modified.append(str(filepath))

            elif operation == "update":
                if filepath.exists():
                    existing = filepath.read_text(encoding="utf-8")
                    find_text = op.get("find", "")
                    if find_text and find_text in existing:
                        updated = existing.replace(find_text, op["content"], 1)
                        filepath.write_text(updated, encoding="utf-8")
                        print(f"  Updated: {rel_path}")
                        modified.append(str(filepath))
                    else:
                        print(f"  Skip update (find text not found): {rel_path}")
                else:
                    print(f"  Skip update (file not found): {rel_path}")

        except OSError as e:
            print(f"  Error applying operation to {rel_path}: {e}")

    return modified


def update_index_files_table(category_dir: str, new_files: list[str]) -> None:
    """Add new files to the category's index.md Files table if they exist."""
    index_path = Path(category_dir) / "index.md"
    if not index_path.exists():
        return

    content = index_path.read_text(encoding="utf-8")
    cat_root = Path(category_dir)

    for fpath in new_files:
        fp = Path(fpath)
        if not str(fp).startswith(str(cat_root)):
            continue
        rel = fp.relative_to(cat_root)
        if str(rel) == "index.md":
            continue

        entry = f"| [{rel}](./{rel}) |  |"
        if str(rel) not in content:
            content = content.rstrip() + f"\n{entry}\n"

    index_path.write_text(content, encoding="utf-8")


def git_commit_and_push(repo_root: str, message: str) -> bool:
    """Stage all changes, commit, and push."""
    try:
        subprocess.run(
            ["git", "config", "user.name", "Persona Questionnaire Agent"],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "questionnaire-agent@persona.local"],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "add", "-A"],
            cwd=repo_root, check=True, capture_output=True,
        )

        diff = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            cwd=repo_root, capture_output=True,
        )
        if diff.returncode == 0:
            return False

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_root, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=repo_root, check=True, capture_output=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git error: {e.stderr.decode() if e.stderr else e}")
        return False
