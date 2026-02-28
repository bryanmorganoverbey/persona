---
last_reviewed: 2026-02-28
proposal: A
status: proposed
---

# Proposal A: GitHub Actions + Claude API

This is the closest to the original idea. A GitHub Actions cron job polls for incomplete goals, calls the Claude API to execute them, and uses Telegram for clarification.

## Architecture

```
GitHub Actions (cron every 2 hours)
  ├── Scanner step: Parse goal files, find incomplete tasks
  ├── Planner step: Create attempt file, commit to repo
  ├── Executor step: Call Claude API with web search + code execution tools
  ├── Clarifier step: If blocked, send Telegram message, wait for reply
  └── Reporter step: Write results to goal folder, commit to repo
```

## Runtime

- **Where:** GitHub-hosted runners (Ubuntu)
- **Trigger:** Cron schedule every 2 hours (`0 */2 * * *`)
- **Max runtime:** 6 hours per job (GitHub-hosted limit) — more than enough for most tasks
- **Concurrency:** One job at a time (use `concurrency` setting to prevent overlap)

## Agent / LLM

- **Claude API** (Sonnet 4.6 for cost efficiency, Opus 4.6 for complex tasks)
- **Tool use enabled:**
  - `web_search_20260209` — real-time web search for research tasks
  - `web_fetch_20260209` — fetch full page content
  - `code_execution_20250825` — run code in sandboxed environment
- **Programmatic tool calling** (`code_execution_20260120`) for multi-step research workflows

## How It Works

### Step 1: Scan for Incomplete Goals

```bash
# Find all goal index.md files for the current month
MONTH=$(date +%m)
GOALS_DIR="vision_boards/2026/${MONTH}/goals"

# Parse each goal's index.md for unchecked tasks
# Filter by status != completed in frontmatter
```

A Python or bash script reads each goal's `index.md`, extracts:
- `status` from frontmatter (skip if `completed` or `failed`)
- Unchecked `- [ ]` items as individual tasks
- `deadline` for prioritization (urgent tasks first)

### Step 2: Create an Attempt

For each task, create a file at:
```
goals/<goal-name>/attempts/YYYY-MM-DD-HH-attempt.md
```

Contents:
```markdown
---
task: "Research airframe designs suitable for solar panels"
goal: solar-glider-research
started: 2026-03-15T14:00:00Z
status: in_progress
---

# Attempt: Research airframe designs suitable for solar panels

## Plan
1. Search for RC solar glider airframe designs
2. Compare foam, balsa, and composite options
3. Evaluate wing area needed for solar panel mounting
4. Summarize findings with links and recommendations
```

Commit this file before executing so there's a record of the plan.

### Step 3: Execute via Claude API

Call the Claude API with:
- System prompt containing the goal context, persona profile, and task description
- Tools enabled: web search, web fetch, code execution
- Max tokens budget per task (configurable, default ~4000 output tokens)

```python
import anthropic

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-6-20260209",
    max_tokens=4096,
    system="You are an autonomous agent executing goals from a personal vision board...",
    tools=[
        {"type": "web_search_20260209"},
        {"type": "web_fetch_20260209"},
        {"type": "code_execution_20250825"}
    ],
    messages=[{"role": "user", "content": task_prompt}]
)
```

### Step 4: Clarification via Telegram

If the agent determines it needs input:

```yaml
- name: Ask clarification via Telegram
  uses: cbrgm/telegram-github-action@v1
  with:
    token: ${{ secrets.TELEGRAM_BOT_TOKEN }}
    to: ${{ secrets.TELEGRAM_CHAT_ID }}
    message: |
      🤖 Goal Agent needs your input:

      Goal: ${{ env.GOAL_NAME }}
      Task: ${{ env.TASK_NAME }}
      Question: ${{ env.QUESTION }}

      Reply to this message and re-run the workflow.
```

For waiting on a response, two options:
1. **Simple:** Agent marks the task as `blocked` and moves on. Next poll picks it up if a response file was added.
2. **Interactive:** Use a Telegram bot webhook that triggers a `repository_dispatch` event when a reply comes in.

### Step 5: Report Results

Update the attempt file with results:

```markdown
---
task: "Research airframe designs suitable for solar panels"
goal: solar-glider-research
started: 2026-03-15T14:00:00Z
completed: 2026-03-15T14:12:00Z
status: completed
tokens_used: 3847
cost_estimate: $0.07
---

# Attempt: Research airframe designs suitable for solar panels

## Plan
(original plan)

## Results
(detailed findings, links, recommendations)

## Files Created
- airframe-options.md — comparison table of airframe designs
```

Also update the goal's `index.md` to check off the completed task and update the frontmatter status.

## Secrets Required

| Secret | Purpose |
|--------|---------|
| `ANTHROPIC_API_KEY` | Claude API access |
| `TELEGRAM_BOT_TOKEN` | Telegram bot for clarification |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

## Cost Estimate

| Component | Cost |
|-----------|------|
| GitHub Actions | Free (2,000 min/month on free tier, 3,000 on Pro) |
| Claude Sonnet 4.6 | ~$0.05-0.50 per task (depending on complexity) |
| Claude Opus 4.6 | ~$0.15-1.50 per task (for complex reasoning) |
| Telegram Bot | Free |
| **Monthly estimate** | **$5-30** (assuming 5-10 tasks/day) |

## Pros

- **No infrastructure to manage** — GitHub Actions handles compute, scheduling, and secrets
- **Full audit trail** — every attempt is a git commit
- **Web access** — Claude API has built-in web search and fetch tools
- **Cheap** — GitHub Actions free tier is generous, Claude API costs are low per task
- **Telegram is easy** — pre-built GitHub Action, no complex API setup
- **Familiar stack** — you already use GitHub Actions and Claude

## Cons

- **6-hour job limit** on GitHub-hosted runners (fine for most tasks, problematic for very long research)
- **No persistent state between runs** — each job starts fresh, must read state from repo files
- **Telegram clarification is async** — agent can't wait for a real-time reply within the same job
- **Claude API web tools can't render JavaScript** — some websites won't work
- **Rate limits** — GitHub Actions has usage limits on free tier

## Implementation Effort

**Estimated time:** 2-3 days for a working MVP

1. Day 1: Scanner + planner (parse goals, create attempt files)
2. Day 2: Executor (Claude API integration with tool use)
3. Day 3: Reporter + Telegram integration + testing
