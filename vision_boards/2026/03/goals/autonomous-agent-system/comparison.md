---
last_reviewed: 2026-02-28
---

# Architecture Comparison

Side-by-side evaluation of all four proposals for the autonomous goal execution system.

## Summary Matrix

| Dimension | A: GH Actions + Claude | B: Claude Code CLI | C: AWS Step Functions | D: Codex Action |
|-----------|----------------------|-------------------|---------------------|-----------------|
| **Setup time** | 2-3 days | 1 day | 5-7 days | 0.5-1 day |
| **Monthly cost** | $5-30 | $5-40 | $8-40 | $5-25 |
| **Complexity** | Medium | Low | High | Low |
| **Agent capability** | High (web search, code) | Highest (full CLI) | High (web search, code) | Medium (code-focused) |
| **Web research** | Native (Claude tools) | Native (Claude tools) | Native (Claude tools) | Limited |
| **Clarification** | Telegram (async) | Telegram (sync possible) | Telegram (true wait) | File-based (clunky) |
| **Max runtime** | 6 hours | Unlimited | Unlimited | 6 hours |
| **Infrastructure** | None (GitHub) | VM or local machine | AWS (serverless) | None (GitHub) |
| **Monitoring** | GitHub Actions UI | Log files | AWS Console (visual) | GitHub Actions UI |
| **Audit trail** | Git commits | Git commits | Git + CloudWatch | Git commits |
| **Reliability** | Good | Machine-dependent | Excellent | Good |
| **Vendor** | GitHub + Anthropic | Anthropic | AWS + Anthropic | GitHub + OpenAI |

## Detailed Comparison

### Agent Capability

| Capability | A | B | C | D |
|-----------|---|---|---|---|
| Web search | ✅ Claude tool | ✅ Claude tool | ✅ Claude tool | ❌ Limited |
| Web page fetch | ✅ Claude tool | ✅ Claude tool | ✅ Claude tool | ❌ |
| Code execution | ✅ Sandboxed | ✅ Full shell | ✅ Sandboxed | ✅ Sandboxed |
| File editing | ✅ Via API | ✅ Native | ✅ Via API | ✅ Native |
| Git operations | ✅ Shell step | ✅ Native | ✅ Lambda | ✅ Shell step |
| MCP tools | ❌ | ✅ | ❌ | ❌ |
| Session resume | ❌ | ✅ | N/A (stateful) | ❌ |
| JavaScript rendering | ❌ | ❌ | ❌ | ❌ |

### Clarification / Human-in-the-Loop

| Aspect | A | B | C | D |
|--------|---|---|---|---|
| Send question | Telegram action | curl to Telegram | Lambda + Telegram | File + Telegram notify |
| Receive answer | Async (next run) | Poll or webhook | True wait (callback) | File edit (next run) |
| Wait without cost | ❌ (job ends) | ❌ (machine runs) | ✅ (Step Functions pauses) | ❌ (job ends) |
| Real-time reply | ❌ | ✅ (if polling) | ✅ | ❌ |
| Latency | 2 hours (next cron) | Minutes (if polling) | Seconds (callback) | 2 hours (next cron) |

### Operational

| Aspect | A | B | C | D |
|--------|---|---|---|---|
| Uptime dependency | GitHub | Your machine | AWS | GitHub |
| Failure recovery | Re-run job | Manual | Auto-retry | Re-run job |
| Concurrent goals | Sequential | Sequential | Parallel (Map state) | Sequential |
| Secrets management | GitHub Secrets | Env vars | AWS Secrets Manager | GitHub Secrets |
| IaC support | Workflow YAML | N/A | Terraform | Workflow YAML |

## Recommendation

### For fastest MVP: **Proposal B (Claude Code CLI)**

- 1 day to implement
- Most capable agent (full Claude Code with all tools)
- You already use Claude Code daily
- Run on a $6/month DigitalOcean droplet or your laptop
- Upgrade to Proposal A or C later once the concept is proven

### For best balance: **Proposal A (GitHub Actions + Claude API)**

- 2-3 days to implement
- No infrastructure to manage
- Strong web research capability via Claude tools
- Clean git audit trail
- Telegram integration is straightforward
- Closest to your original idea

### For production-grade: **Proposal C (AWS Step Functions)**

- 5-7 days to implement
- True wait-for-callback (agent pauses while you reply on Telegram)
- Built-in retry, error handling, visual monitoring
- You already use Terraform and AWS
- Overkill for current scale but built to grow

### Skip unless OpenAI-preferred: **Proposal D (Codex Action)**

- Simplest implementation but weakest capabilities
- No web research — bad fit for non-code goals like housing search
- Only choose this if you specifically want to use OpenAI models

## Suggested Path

1. **Start with Proposal B** — get a working prototype in a day. Run it on your laptop or a cheap VM. Validate the loop works: scan → plan → execute → report.
2. **Graduate to Proposal A** — once proven, move to GitHub Actions for reliability and no-machine dependency. Add Telegram for clarification.
3. **If scale demands it, evolve to Proposal C** — when you have many goals, need parallel execution, or want true wait-for-callback, invest in the AWS architecture.
