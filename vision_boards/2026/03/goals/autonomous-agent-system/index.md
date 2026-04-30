---
last_reviewed: 2026-02-28
confidence: high
status: completed
---

# Build Autonomous Goal Execution System

## Goal

Create a continuously running autonomous system that polls for incomplete goals in the persona repo's vision boards, autonomously attempts to complete them, asks clarifying questions via messaging when needed, and writes results back to the repo.

## Architecture: Proposal A (GitHub Actions + Claude API)

Selected architecture. See [proposal-a-github-actions-claude.md](./proposal-a-github-actions-claude.md) for the full design.

```
GitHub Actions (cron every 2 hours)
  └── scripts/goal-agent/main.py
       ├── scanner.py  — parse goal files, build prioritized work queue
       ├── executor.py — call Claude API with web search + code execution
       ├── reporter.py — write attempt files, update goals, commit to repo
       └── telegram.py — send notifications and clarification questions
```

## Implementation

| Component | File | Status |
|-----------|------|--------|
| Scanner | `scripts/goal-agent/scanner.py` | Done |
| Executor | `scripts/goal-agent/executor.py` | Done |
| Reporter | `scripts/goal-agent/reporter.py` | Done |
| Telegram | `scripts/goal-agent/telegram.py` | Done |
| Orchestrator | `scripts/goal-agent/main.py` | Done |
| Workflow | `.github/workflows/goal-agent.yml` | Done |
| Dependencies | `scripts/goal-agent/requirements.txt` | Done |

## Setup Required (Secrets)

Before the agent can run, add these GitHub repository secrets:

| Secret | Purpose | How to Get |
|--------|---------|------------|
| `MINIMAX_API_KEY` | MiniMax API access | [platform.minimax.io](https://platform.minimax.io/) |
| `BRAVE_SEARCH_API_KEY` | Web search tool | [brave.com/search/api](https://brave.com/search/api/) (free tier: 2,000 queries/month) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot | Message [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | Message [@userinfobot](https://t.me/userinfobot) on Telegram |

## How It Works

1. **Every 2 hours**, GitHub Actions triggers `goal-agent.yml`
2. **Scanner** reads `vision_boards/2026/MM/goals/*/index.md` for the current month
3. Tasks are prioritized by deadline (urgent first) and status (in-progress before not-started)
4. **Work queue** is capped at 3 tasks per run (configurable via `GOAL_AGENT_MAX_TASKS`)
5. For each task:
   - Creates an **attempt file** with the plan, commits it
   - **Executes** via MiniMax API with web_search and web_fetch tools (agentic loop, up to 15 rounds)
   - If blocked, sends a **Telegram message** asking for clarification
   - If successful, writes results back, **checks off the task**, and updates goal status
   - **Commits** all changes to the repo
6. Sends a **run summary** via Telegram

## Tasks

- [x] Choose architecture (review proposals A-D)
- [x] Set up Telegram bot for clarification questions
- [x] Define task schema and parsing logic
- [x] Implement the scanner (find incomplete goals for current month)
- [x] Implement the planner (create attempt files)
- [x] Implement the executor (spin up LLM agent)
- [x] Implement the reporter (write results back, commit)
- [x] Implement safety boundaries and permission checks
- [x] Add GitHub secrets (MINIMAX_API_KEY, BRAVE_SEARCH_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- [x] Test with a low-risk goal (e.g., research task)
- [x] Deploy and monitor first autonomous run
