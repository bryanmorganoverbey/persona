---
last_reviewed: 2026-02-28
proposal: B
status: proposed
---

# Proposal B: Claude Code CLI + claun Scheduler

Use Claude Code (the same agent you already use in Cursor) running headlessly from the command line, scheduled by `claun` or a system cron job. This keeps the agent local, stateful, and capable of doing everything Cursor can do — file edits, shell commands, web access — without GitHub Actions overhead.

## Architecture

```
Local machine or cloud VM (always-on)
  └── claun / cron scheduler (every 2 hours)
       └── claude -p "scan and execute goals" --allowedTools "..."
            ├── Reads goal files from the local repo clone
            ├── Plans and executes tasks using full Claude Code capabilities
            ├── Sends Telegram messages via curl for clarification
            ├── Commits results back to the repo
            └── Pushes to GitHub
```

## Runtime

- **Where:** Your laptop (when open), a cloud VM (DigitalOcean, EC2, etc.), or a Raspberry Pi
- **Scheduler:** `claun` (purpose-built for scheduling Claude Code jobs) or system crontab
- **Max runtime:** No hard limit — runs as long as needed
- **State:** Persistent — same filesystem between runs, can resume sessions

## Agent / LLM

- **Claude Code CLI** in headless mode (`claude -p "..." --output-format json`)
- Full tool access: Read, Write, Shell, Grep, Glob, web search, web fetch, MCP tools
- Can use `--resume` flag to continue a previous session (maintains context across runs)
- Configurable `--allowedTools` to restrict what the agent can do autonomously
- `--max-turns` to limit how far the agent goes before stopping

## How It Works

### Step 1: Scheduled Trigger

Using `claun`:
```bash
claun -H -c "Read vision_boards/2026/$(date +%m)/goals/*/index.md. \
  Find tasks with unchecked [ ] items. For each task, create an attempt \
  plan, execute it using web search and research tools, and write results \
  back. Commit changes." \
  -m 120 --timeout 3600
```

Or via crontab:
```cron
0 */2 * * * cd /path/to/persona && claude -p "$(cat .github/agent-prompt.md)" \
  --allowedTools "Read,Write,Shell,Glob,Grep" \
  --output-format json >> /var/log/goal-agent.log 2>&1
```

### Step 2: Agent Prompt

Store a reusable prompt at `.github/agent-prompt.md`:
```markdown
You are an autonomous goal execution agent for my persona repo.

1. Read the current month's vision board goals from vision_boards/2026/MM/goals/*/index.md
2. Find tasks with unchecked [ ] items where status is not "completed" or "failed"
3. For each task:
   a. Create an attempt file at goals/<name>/attempts/YYYY-MM-DD-HH-attempt.md with your plan
   b. Execute the task (research, write, analyze, etc.)
   c. Write results back to the attempt file and any new files in the goal folder
   d. Check off the completed task in the goal's index.md
   e. Commit all changes with a descriptive message
4. If you need clarification, run: curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" -d "chat_id=${TELEGRAM_CHAT_ID}" -d "text=<your question>"
5. Push all commits to origin when done
```

### Step 3: Execution

Claude Code has full shell access, so it can:
- Run `git commit` and `git push` directly
- Execute `curl` for Telegram messages
- Run Python scripts for data analysis
- Use web search and fetch tools for research
- Create and edit files with its native Write/StrReplace tools

### Step 4: Clarification via Telegram

Since Claude Code has shell access, it can send Telegram messages directly:
```bash
curl -s "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
  -d "chat_id=${CHAT_ID}" \
  -d "text=🤖 I'm working on: ${GOAL}. Question: ${QUESTION}"
```

For receiving responses, options:
1. **Poll for replies:** Agent checks Telegram `getUpdates` endpoint periodically
2. **Webhook to file:** A lightweight webhook server writes replies to a file the agent checks
3. **Skip and retry:** Mark as blocked, pick up on next run if a response was added to the repo

### Step 5: Report Back

Same as Proposal A — create attempt files, update goal index, commit and push.

## Secrets / Environment

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Already set if you use Claude Code |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

## Cost Estimate

| Component | Cost |
|-----------|------|
| Claude Code CLI | Uses your existing Anthropic API key / Claude subscription |
| Cloud VM (if not local) | ~$5-12/month (DigitalOcean droplet or small EC2) |
| Telegram Bot | Free |
| **Monthly estimate** | **$5-40** (depending on task volume and model used) |

If you have a Claude Max subscription, Claude Code usage may be included, making the LLM cost effectively zero.

## Pros

- **Most capable agent** — Claude Code can do everything Cursor does: file editing, shell commands, git, web search, MCP tools
- **No job time limits** — runs as long as needed, unlike GitHub Actions' 6-hour cap
- **Stateful** — persistent filesystem, can resume sessions with `--resume`
- **Already familiar** — you use Claude Code / Cursor daily
- **Simplest implementation** — it's essentially one cron job running one CLI command
- **Full local access** — can interact with other local tools, databases, APIs
- **Session persistence** — `claun` supports resuming previous sessions for multi-run tasks

## Cons

- **Requires an always-on machine** — your laptop sleeps, a VM costs money
- **No built-in audit trail in a web UI** — you get git commits but no dashboard
- **Security risk** — full shell access means the agent can do anything on the machine
- **Single point of failure** — if the machine goes down, no goals get executed
- **Harder to monitor remotely** — no GitHub Actions UI to check run status
- **Git conflicts** — if you're also editing the repo, push/pull conflicts can occur

## Implementation Effort

**Estimated time:** 1 day for a working MVP

1. Write the agent prompt (2 hours)
2. Set up claun or cron (30 minutes)
3. Set up Telegram bot (30 minutes)
4. Test with a research task (2-3 hours)

## When to Choose This

Pick this if you want the **fastest path to a working prototype** and you're comfortable running it on a VM or your laptop. This is the "just get it running" option.
