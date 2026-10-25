# NOVA Engineering Agents — executable MVP

Real FastAPI service with password-protected admin panel, workspace project selection, persistent SQLite task/event history, Codex CLI task execution, and Coding -> pytest -> Debug -> pytest automatic handoff (up to two debug retries). Other agents (Database, Browser, DevOps, Testing) are selectable but execute one Codex role each; they do **not** execute database migrations, browser automation or deployments autonomously. n8n integration is provided as import-ready example workflows; it is not connected until you configure and activate them.

## Ubuntu installation (isolated; does not touch existing Docker/apps)

```bash
sudo apt update
sudo apt install -y python3-venv
mkdir -p /opt/agent-engineer-real
# Extract contents of ZIP into /opt/agent-engineer-real
cd /opt/agent-engineer-real
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# install Codex CLI separately with Node/npm if not already available
codex --version
codex login
export ADMIN_PASSWORD='REPLACE_WITH_A_LONG_UNIQUE_PASSWORD'
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

Access via SSH forwarding on your own PC: `ssh -L 8765:127.0.0.1:8765 USER@SERVER` then open http://127.0.0.1:8765 and log in as `admin` with your `ADMIN_PASSWORD`.

**Important:** Codex CLI must be authenticated *as the same operating-system user that runs uvicorn*. Codex CLI and Python tools run under that user's permissions. Run under a dedicated unprivileged user, never root, and keep workspace away from live deployments or secrets. Codex `workspace-write` sandbox is a defense in depth; it does not substitute for a process/container security boundary. Use a dedicated container/VM with limited filesystem and network access before exposing this externally. Do not bind `0.0.0.0` without HTTPS/auth hardening. No production readiness claims.

## Test without Codex (real API/SQLite/test orchestration; fake editing)

```bash
export ADMIN_PASSWORD='local-test-password'
export MOCK_CODEX=1
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

Enter `sample` project and Coding Agent. In mock mode the worker creates `agent_output.txt`, runs real pytest, saves events and results. This proves handoffs and UI plumbing only—not AI/code-editing quality. Remove MOCK_CODEX when ready to use Codex.

## Behavior and limitations

- Only existing direct-child directories under AGENT_WORKSPACE can be selected; symbolic links rejected.
- Coding/Debug agents use `codex exec --sandbox workspace-write --ask-for-approval never`; sandbox refusal leads to failure rather than escalation. Commands are argument arrays, not a shell string.
- Test stage executes `python -m pytest -q tests` from the project. Tests execute arbitrary project code, so **only use trusted projects in an isolated worker**.
- Task worker uses a simple Python thread, not a durable queue: if service restarts, running jobs may remain `running` and need manual review. Production needs job queue, concurrency limits, restart reconciliation, stronger authorization, and per-task sandbox isolation.
- No automated external connections, GitHub pushes, deployments, database writes, remote SSH, or Windows workers.
- SQLite holds task prompt and Codex output: don't submit secrets.
- Running multiple workers against the same SQLite DB is not supported. Start one Uvicorn worker.

## NEW: Telegram + Admin Panel + n8n connection

All task creation/status/history use the SAME backend and SQLite database. Telegram is an independent long-polling process. The admin panel stays at `/`, with task monitoring and a cooperative cancel-request button. Telegram uses `/run PROJECT AGENT auto|manual | TASK`, `/projects`, `/tasks`, `/status TASK_ID`, `/cancel TASK_ID`.

**Environment:** do not put credentials in Git. Set `ADMIN_PASSWORD`, `AGENT_API_KEY` (random 48+ byte secret), `TELEGRAM_BOT_TOKEN` (from BotFather), `TELEGRAM_ALLOWED_IDS` (your Telegram numeric user IDs) in the shell/systemd environment. `.env.example` is merely a template: neither Python process automatically loads `.env`. Start API then, in a separate shell with same variables:

```bash
python3 telegram_bot.py
```

Telegram bot uses Telegram HTTPS long-polling and never opens inbound Telegram ports. Both interfaces submit to the existing `/api/tasks` endpoint. Avoid running another bot instance with the same token (polling collision). Keep backend bound to localhost. Use SSH tunneling or a correctly configured authenticated HTTPS proxy for the admin panel.

### n8n

`n8n/notification-example.json` is an **inactive example**, not deployed or connected. For duplicate-safe polling, import `n8n/notification-dedup-example.json`, select your Telegram credential, set `AGENT_API_KEY` and `TELEGRAM_NOTIFY_CHAT_ID`, and adapt the backend URL for your Docker network (`host.docker.internal` is not automatically available on Linux). The dedup workflow uses `/api/tasks/terminal?after=CURSOR` and n8n workflow static data. It also does not yet do task submission; API integration can be configured through n8n HTTP Request node `POST /api/tasks` using `X-Agent-Key`. If n8n blocks `$env` expressions, configure the header via n8n credentials instead. Ensure n8n can only reach the intended backend address.

**Cancellation:** `/cancel` sets `cancel_requested` and stops the active Codex/pytest process tree when possible. Cancellation does not rollback file edits; interrupted tasks still require manual inspection.

**Queue protection:** `AGENT_MAX_QUEUE_SIZE` limits queued/active tasks (default `100`) and returns HTTP `429` when full. Event and result text applies basic redaction for common API keys, tokens, passwords and bearer values; do not submit secrets in prompts.

**Not production complete:** database is still SQLite, task runners still daemon threads, API key is shared, no push notifications by default, no Telegram inline keyboard, and no restart-safe job recovery. Security audits, durable queue and worker isolation required before internet exposure.

`n8n/task-submit-example.json` adds a sample webhook-to-API flow (INACTIVE). **Do not expose/activate this webhook without n8n authentication, IP controls, project authorization, rate limits and proper URL configuration.** Telegram already submits directly; n8n is optional and useful for external triggers/schedules.

## Version 0.3 update — Telegram button flow and serial task queue

Telegram: send `/new` to open project selection buttons, then choose an agent, choose **automatic handoff** or **single agent**, and send the task as plain text. Existing `/run ...` commands remain available. The draft conversation is temporarily held in bot memory; `/new` resets it. Telegram inline callbacks require a single polling bot instance. No Telegram live test has been performed without user credentials.

Backend tasks are now run serially through an in-process queue consumer (one job at a time) instead of launching unbounded threads. `queued` tasks survive normal restarts and will run when the API starts. Jobs interrupted while `running`/`starting` are marked `interrupted` for manual inspection, **not** replayed automatically. Pending cancellation is resolved to `cancelled` on restart. This is still not a distributed production queue and must run with **one Uvicorn process / worker only**. Keep a durable backup of the task database separately.

Local API test verified auth, task submission, sample pytest auto-run, completed state, persistent events and queued cancellation with mock Codex. Actual Codex, Telegram account, and n8n connections remain unverified.

For a user-friendly install: unzip to a dedicated **unprivileged** user's directory such as `/home/aiagent/engineering-agents`; do not extract over a running service. `export` variables in the API terminal AND bot terminal. Never share tokens in chat. Set permissions and verify `codex --version`, `codex login status` for the same service user. Do not point `AGENT_WORKSPACE` at existing live projects: import a disposable copy first.
