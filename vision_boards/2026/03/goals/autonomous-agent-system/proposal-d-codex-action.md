---
last_reviewed: 2026-02-28
proposal: D
status: proposed
---

# Proposal D: OpenAI Codex GitHub Action

Use OpenAI's official Codex GitHub Action (`openai/codex-action@v1`) as the execution engine. Codex is a lightweight coding agent designed for CI/CD pipelines. This is the simplest possible approach — a single GitHub Action step that runs Codex with a prompt.

## Architecture

```
GitHub Actions (cron every 2 hours)
  └── openai/codex-action@v1
       ├── Reads goal files from the checked-out repo
       ├── Executes tasks using Codex's built-in capabilities
       ├── Writes results back to the repo
       └── Commits and pushes changes
```

## Runtime

- **Where:** GitHub-hosted runners
- **Trigger:** Cron schedule every 2 hours
- **Max runtime:** 6 hours (GitHub-hosted limit)
- **Agent:** OpenAI Codex CLI running inside the GitHub Action

## Agent / LLM

- **OpenAI Codex** — a coding agent with file editing, shell execution, and web access
- Runs in configurable sandbox modes:
  - `read-only` — can only read files (for planning/analysis)
  - `workspace-write` — can read/write files in the workspace
  - `danger-full-access` — full system access (needed for git push, curl, etc.)

## How It Works

### Workflow File

```yaml
name: Execute Vision Board Goals

on:
  schedule:
    - cron: '0 */2 * * *'
  workflow_dispatch:

concurrency:
  group: goal-executor
  cancel-in-progress: false

jobs:
  execute-goals:
    runs-on: ubuntu-latest
    timeout-minutes: 60
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Execute goals with Codex
        uses: openai/codex-action@v1
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          safety-strategy: workspace-write
          prompt: |
            You are an autonomous goal execution agent. Your job:

            1. Read vision_boards/2026/$(date +%m)/goals/*/index.md
            2. Find tasks with unchecked [ ] items (status != completed)
            3. For each incomplete task:
               a. Create an attempt file: goals/<name>/attempts/$(date +%Y-%m-%d-%H)-attempt.md
               b. Execute the task (research, write, analyze)
               c. Write results to the attempt file
               d. Check off the task in the goal's index.md
            4. If you need to ask me something, write the question to a file:
               goals/<name>/questions/$(date +%Y-%m-%d-%H)-question.md

      - name: Commit results
        run: |
          git config user.name "Goal Agent"
          git config user.email "agent@goals.local"
          git add -A
          git diff --staged --quiet || git commit -m "agent: execute vision board goals $(date +%Y-%m-%d-%H)"
          git push

      - name: Notify via Telegram if questions exist
        if: always()
        run: |
          MONTH=$(date +%m)
          QUESTIONS=$(find vision_boards/2026/${MONTH}/goals/*/questions -name "*.md" -newer .git/FETCH_HEAD 2>/dev/null)
          if [ -n "$QUESTIONS" ]; then
            MESSAGE="🤖 Goal Agent has questions:\n\n"
            for q in $QUESTIONS; do
              MESSAGE="${MESSAGE}$(head -5 $q)\n\n"
            done
            curl -s "https://api.telegram.org/bot${{ secrets.TELEGRAM_BOT_TOKEN }}/sendMessage" \
              -d "chat_id=${{ secrets.TELEGRAM_CHAT_ID }}" \
              -d "text=${MESSAGE}" \
              -d "parse_mode=Markdown"
          fi
```

### Clarification Handling

Since Codex runs inside GitHub Actions and can't wait for Telegram replies, this proposal uses a **question file** pattern:

1. Agent writes questions to `goals/<name>/questions/YYYY-MM-DD-HH-question.md`
2. Telegram notification alerts you that questions exist
3. You answer by editing the question file (add an `## Answer` section) and pushing
4. Next scheduled run picks up the answer and continues

## Secrets Required

| Secret | Purpose |
|--------|---------|
| `OPENAI_API_KEY` | Codex / OpenAI API access |
| `TELEGRAM_BOT_TOKEN` | Telegram notifications |
| `TELEGRAM_CHAT_ID` | Your chat ID |

## Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| GitHub Actions | Free tier (2,000-3,000 min/month) |
| OpenAI Codex | ~$5-25 (depends on model and usage) |
| Telegram Bot | Free |
| **Monthly total** | **$5-25** |

## Pros

- **Simplest implementation** — literally one workflow file, ~50 lines of YAML
- **Official GitHub Action** — maintained by OpenAI, designed for CI/CD
- **Built-in sandboxing** — configurable safety levels (read-only, workspace-write, full access)
- **No infrastructure** — runs entirely on GitHub Actions
- **Version-pinned** — can pin specific Codex CLI versions for reproducibility
- **Familiar** — it's just a GitHub Action, same as your staleness checker

## Cons

- **OpenAI, not Claude** — uses GPT/Codex models, not Claude. Different capabilities, potentially different quality for research tasks
- **No built-in web search** — Codex is primarily a coding agent. Web research capabilities are more limited than Claude's tool use
- **6-hour GitHub Actions limit** applies
- **Question files are clunky** — async clarification via file edits is less natural than a Telegram conversation
- **Less capable for non-code tasks** — Codex excels at code changes but may struggle with tasks like "research Nashville housing" compared to Claude with web search
- **No real-time clarification** — can't pause and wait for a reply

## Implementation Effort

**Estimated time:** 0.5-1 day

1. Write the workflow file (1-2 hours)
2. Set up secrets (15 minutes)
3. Test with a simple goal (2-3 hours)

## When to Choose This

Pick this if you want the **absolute simplest possible implementation** and you're okay with OpenAI models instead of Claude. Best as a quick proof-of-concept to validate the autonomous loop before investing in a more capable system.
