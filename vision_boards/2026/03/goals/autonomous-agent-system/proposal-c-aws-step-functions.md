---
last_reviewed: 2026-02-28
proposal: C
status: proposed
---

# Proposal C: AWS Step Functions + Lambda

A cloud-native, event-driven architecture using AWS services. Step Functions orchestrates the workflow, Lambda functions handle each step, and EventBridge triggers the schedule. Built for reliability, observability, and scale — but significantly more complex to set up.

## Architecture

```
EventBridge Scheduler (every 2 hours)
  └── Step Functions State Machine
       ├── Lambda: scan-goals
       │   └── Clone repo, parse goal files, build task queue
       ├── Lambda: plan-attempt
       │   └── Create attempt file, commit to repo
       ├── Lambda: execute-task
       │   └── Call Claude API with tools, execute the task
       ├── Choice: needs-clarification?
       │   ├── Yes → Lambda: send-telegram + Wait for callback
       │   └── No → continue
       ├── Lambda: report-results
       │   └── Write results, update goal, commit, push
       └── Map state: process next task (parallel or sequential)
```

## Runtime

- **Where:** AWS (fully serverless — no machines to manage)
- **Trigger:** EventBridge scheduled rule every 2 hours
- **Max runtime:** Step Functions can run for up to 1 year; individual Lambdas up to 15 minutes (or use Lambda Durable Functions for longer)
- **State:** Managed by Step Functions — each step's output feeds the next
- **Concurrency:** Built-in — can process multiple goals in parallel via Map state

## Agent / LLM

- **Claude API** called from Lambda functions via the Anthropic Python SDK
- Same tool use as Proposal A: web search, web fetch, code execution
- Could also invoke **Bedrock** for Claude access with IAM-based auth (no API key management)

## How It Works

### Step 1: EventBridge Trigger

```json
{
  "ScheduleExpression": "rate(2 hours)",
  "Target": {
    "Arn": "arn:aws:states:us-east-1:ACCOUNT:stateMachine:GoalExecutor"
  }
}
```

### Step 2: State Machine Definition

```json
{
  "StartAt": "ScanGoals",
  "States": {
    "ScanGoals": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:...:scan-goals",
      "Next": "HasTasks?"
    },
    "HasTasks?": {
      "Type": "Choice",
      "Choices": [
        { "Variable": "$.tasks", "IsPresent": true, "Next": "ProcessTasks" }
      ],
      "Default": "NoTasksFound"
    },
    "ProcessTasks": {
      "Type": "Map",
      "ItemsPath": "$.tasks",
      "Iterator": {
        "StartAt": "PlanAttempt",
        "States": {
          "PlanAttempt": { "Type": "Task", "Resource": "...:plan-attempt", "Next": "ExecuteTask" },
          "ExecuteTask": { "Type": "Task", "Resource": "...:execute-task", "Next": "NeedsClarification?" },
          "NeedsClarification?": {
            "Type": "Choice",
            "Choices": [
              { "Variable": "$.needsClarification", "BooleanEquals": true, "Next": "SendTelegram" }
            ],
            "Default": "ReportResults"
          },
          "SendTelegram": { "Type": "Task", "Resource": "...:send-telegram", "Next": "WaitForReply" },
          "WaitForReply": {
            "Type": "Task",
            "Resource": "arn:aws:states:::sqs:receiveMessage.waitForTaskToken",
            "TimeoutSeconds": 86400,
            "Next": "ExecuteTask"
          },
          "ReportResults": { "Type": "Task", "Resource": "...:report-results", "End": true }
        }
      },
      "Next": "Done"
    },
    "NoTasksFound": { "Type": "Succeed" },
    "Done": { "Type": "Succeed" }
  }
}
```

### Step 3: Clarification with Wait-for-Callback

This is where Step Functions shines. The `WaitForReply` state uses a **task token** pattern:

1. Lambda sends a Telegram message with the question
2. Step Functions pauses (no compute cost while waiting)
3. A Telegram bot webhook receives your reply
4. The webhook calls Step Functions `SendTaskSuccess` with the reply and the task token
5. The state machine resumes with your answer

This means the agent can genuinely wait for your response — no polling, no retries, no wasted compute.

### Step 4: Git Integration

Each Lambda clones the repo (or uses a shared EFS mount), makes changes, commits, and pushes. Use a deploy key or GitHub App token stored in AWS Secrets Manager.

## Infrastructure (Terraform)

Since you use Terraform and AWS, this could be defined as IaC:

```hcl
resource "aws_sfn_state_machine" "goal_executor" {
  name     = "persona-goal-executor"
  role_arn = aws_iam_role.step_functions.arn
  definition = file("state-machine.json")
}

resource "aws_scheduler_schedule" "every_2_hours" {
  name       = "goal-executor-schedule"
  schedule_expression = "rate(2 hours)"
  target {
    arn      = aws_sfn_state_machine.goal_executor.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
```

## Secrets Required

| Secret | Location | Purpose |
|--------|----------|---------|
| `ANTHROPIC_API_KEY` | AWS Secrets Manager | Claude API access |
| `TELEGRAM_BOT_TOKEN` | AWS Secrets Manager | Telegram bot |
| `TELEGRAM_CHAT_ID` | AWS Secrets Manager | Your chat ID |
| `GITHUB_DEPLOY_KEY` | AWS Secrets Manager | Push commits to repo |

## Cost Estimate

| Component | Monthly Cost |
|-----------|-------------|
| Step Functions | ~$0.50 (25 state transitions × 12 runs/day × 30 days) |
| Lambda | ~$1-5 (execution time depends on task complexity) |
| EventBridge | Free (2 invocations/day) |
| Claude API (Sonnet 4.6) | ~$5-30 (same as other proposals) |
| Secrets Manager | ~$1.20 (3 secrets) |
| Telegram Bot | Free |
| **Monthly total** | **$8-40** |

## Pros

- **True wait-for-callback** — agent pauses without cost while waiting for Telegram replies. No other proposal can do this.
- **Built-in retry and error handling** — Step Functions retries failed steps automatically
- **Visual execution tracking** — AWS Console shows exactly where each run is, what succeeded, what failed
- **No infrastructure to maintain** — fully serverless
- **Parallel execution** — Map state can process multiple goals simultaneously
- **Durable** — Lambda Durable Functions can run for up to a year for complex tasks
- **Terraform-native** — you already use Terraform and AWS
- **Audit trail** — CloudWatch logs + Step Functions execution history
- **Scales to zero** — no cost when no goals are running

## Cons

- **Most complex to set up** — Step Functions, Lambdas, IAM roles, EventBridge, Secrets Manager, Telegram webhook
- **Significant upfront development time** — 5-7 days for full implementation
- **AWS vendor lock-in** — deeply tied to AWS services
- **Cold starts** — Lambda cold starts add latency (mitigated with provisioned concurrency, but adds cost)
- **Lambda can't run Claude Code CLI** — must use Claude API directly, losing some tool capabilities
- **Overkill for current scale** — you have ~10 goals/month, not 10,000
- **Debugging is harder** — distributed system across multiple Lambdas vs. one script

## Implementation Effort

**Estimated time:** 5-7 days

1. Day 1-2: Terraform infrastructure (Step Functions, Lambdas, IAM, EventBridge)
2. Day 3: Scanner + planner Lambda functions
3. Day 4: Executor Lambda with Claude API integration
4. Day 5: Telegram bot + webhook + wait-for-callback integration
5. Day 6-7: Reporter, testing, monitoring setup

## When to Choose This

Pick this if you want the **most robust, production-grade system** and you're comfortable investing the upfront time. Best if you plan to scale this beyond personal goals (e.g., running it for multiple projects or people).
