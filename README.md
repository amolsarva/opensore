<div align="center">

<p align="center">
  <img src="docs/logo/opensre-logo-white.svg" alt="OpenSRE" width="360" />
</p>

# OpenSRE / opensore 🚀

### Build your own AI SRE agent, run incident investigations, and experiment with local agent workflows.

[![Status](https://img.shields.io/badge/status-local%20alpha-orange?style=for-the-badge)](#)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?style=for-the-badge)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache%202.0-green?style=for-the-badge)](LICENSE)
[![Repo](https://img.shields.io/badge/github-amolsarva%2Fopensore-black?style=for-the-badge&logo=github)](https://github.com/amolsarva/opensore)

</div>

---

## What Is This? 🧠

OpenSRE is an open-source framework for AI-powered site reliability agents. It is designed to take an alert, gather evidence from the systems you already use, reason across that evidence, and produce a root-cause investigation with next steps.

Think of it as an AI incident-investigation workbench:

- 🔎 Pulls context from logs, metrics, traces, cloud systems, runbooks, and chat tools.
- 🧩 Connects to observability, infrastructure, databases, messaging, GitHub, and MCP-style tool surfaces.
- 🧠 Routes work through LLM providers such as OpenAI, Anthropic, OpenRouter, Gemini, Bedrock, Ollama, Codex CLI, and Claude Code.
- 🧪 Includes synthetic and end-to-end incident scenarios so agent behavior can be tested, scored, and improved.
- 💻 Runs locally as a CLI, an interactive shell, or a FastAPI app.

This repo also contains newer experimental directions:

- 🕵️ **Workplace discovery**: workflows for misconduct, retaliation, harassment, and executive-behavior investigations across user-owned evidence exports.
- 🧑‍💻 **Mac personal agent**: local assistant workflows for OpenClaw-like usage, cheap LLMs, WhatsApp, iMessage, and local automation.
- 🐕 **Watchdog workflows**: process monitoring with threshold-triggered Telegram alarms.

> Public alpha: the core flows are usable, but APIs, integrations, and product direction are still moving.

---

## Quickstart ⚡

From a fresh checkout:

```bash
cd ~/Documents/root/opensore
brew install uv          # macOS, if uv is not installed
make install
```

Always run the local checkout with `uv run` so you do not accidentally call another `opensre` binary on your `PATH`:

```bash
uv run opensre --help
uv run opensre doctor
```

Configure an LLM provider:

```bash
uv run opensre onboard
```

Or create a minimal local `.env` yourself:

```bash
LLM_PROVIDER=openai
OPENAI_REASONING_MODEL=gpt-5.4-mini
OPENAI_TOOLCALL_MODEL=gpt-5.4-mini
AWS_PROFILE=amol
AWS_REGION=us-east-1
```

Store API keys in your shell, macOS Keychain, or OpenSRE onboarding flow. Do not commit `.env` files with secrets.

Run the local health app:

```bash
uv run uvicorn app.webapp:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

A healthy local response looks like:

```json
{"ok":true,"version":"0.1","llm_configured":true,"env":"development"}
```

---

## Run Modes 🛠️

### 1. Interactive Shell

Start a terminal REPL for incident triage, slash commands, local tools, and streaming investigations:

```bash
uv run opensre
```

Useful shell commands include:

```text
/help
/doctor
/status
/trust on
/effort high
/exit
```

### 2. One-Shot Investigation

Run an RCA investigation against an alert payload:

```bash
uv run opensre investigate -i tests/e2e/kubernetes/fixtures/datadog_k8s_alert.json
```

### 3. Health App

Run the FastAPI service locally:

```bash
uv run uvicorn app.webapp:app --reload --host 127.0.0.1 --port 8000
```

### 4. Personal Agent Setup

For local assistant and messaging workflows:

```bash
uv run opensre personal doctor
uv run opensre integrations setup whatsapp
uv run opensre messaging pair --platform whatsapp
```

### 5. Watchdog

Monitor a process and alert when thresholds trip:

```bash
uv run opensre watchdog --help
```

---

## How It Works 🧭

When an alert comes in, OpenSRE follows a rough loop:

1. 📥 **Ingest** the alert or user-described incident.
2. 🔌 **Select tools** based on configured integrations and available evidence.
3. 📚 **Gather context** from logs, metrics, traces, tickets, cloud resources, runbooks, and chat.
4. 🧠 **Reason** with the configured LLM provider.
5. 🧾 **Produce an RCA** with probable cause, evidence, confidence, and next actions.
6. 📣 **Deliver results** through the CLI, local app, or configured messaging integrations.

For deeper internals, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/routing-policy-architecture.md](docs/routing-policy-architecture.md), and [docs/investigation-tool-calling.md](docs/investigation-tool-calling.md).

---

## Providers And Integrations 🔌

OpenSRE is designed to work with a broad operations stack.

| Area | Examples |
| --- | --- |
| 🤖 LLMs | OpenAI, Anthropic, OpenRouter, Gemini, NVIDIA NIM, Bedrock, Ollama, Codex CLI, Claude Code |
| 📈 Observability | Grafana, Datadog, Honeycomb, Coralogix, CloudWatch, Sentry, Elasticsearch |
| ☁️ Infrastructure | AWS, Kubernetes, EKS, EC2, Lambda, GCP, Azure |
| 🗄️ Databases | PostgreSQL, MySQL, MariaDB, MongoDB, ClickHouse, Snowflake |
| 🧰 Dev tools | GitHub, GitLab, Bitbucket, MCP, OpenClaw |
| 🚨 Incident tools | PagerDuty, Opsgenie, Jira, Alertmanager |
| 💬 Messaging | Slack, Discord, Telegram, Google Docs, WhatsApp experiments |

Set up integrations with:

```bash
uv run opensre integrations setup <service>
uv run opensre integrations verify <service>
```

List available commands:

```bash
uv run opensre integrations --help
```

---

## Local Development 🧑‍🔧

Install dependencies:

```bash
make install
```

Run common checks:

```bash
make lint
make format-check
make typecheck
make test-cov
```

One-shot quality gate:

```bash
make check
```

Before pushing or opening a PR, follow [CI.md](CI.md). It is the source of truth for required local checks.

---

## Repo Map 🗺️

| Path | Purpose |
| --- | --- |
| `app/` | Core CLI, agent logic, pipeline, services, integrations, tools, state, and web app |
| `tests/` | Unit, integration, synthetic, e2e, deployment, and chaos test suites |
| `docs/` | Product docs, integration guides, design notes, and roadmap docs |
| `.github/` | Workflows, templates, and repo automation |
| `pyproject.toml` | Python package metadata and dependency config |
| `Makefile` | Canonical local commands |
| `SETUP.md` | Local setup and troubleshooting |
| `CI.md` | Required push/PR readiness checklist |

---

## Key Docs 📚

- [SETUP.md](SETUP.md) - install, uv, Windows, troubleshooting, OpenClaw setup
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) - contributor workflow, benchmarks, deployment, telemetry
- [CI.md](CI.md) - mandatory checks before push or PR
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution workflow
- [SECURITY.md](SECURITY.md) - security policy
- [docs/workplace-discovery-product-plan.mdx](docs/workplace-discovery-product-plan.mdx) - workplace discovery direction
- [docs/macos-personal-agent-quickstart.mdx](docs/macos-personal-agent-quickstart.mdx) - Mac personal-agent path
- [docs/personal-agent-roadmap.mdx](docs/personal-agent-roadmap.mdx) - personal-agent roadmap

---

## Deployment 🚢

OpenSRE can run as a standard Python/FastAPI app through the included `Dockerfile` or on platforms such as Railway, EC2, ECS, and Vercel.

At minimum, configure:

```bash
LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

Or:

```bash
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
```

For hosted deployments that need persistence, also configure storage such as `DATABASE_URI` and `REDIS_URI`. See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#deployment).

---

## Privacy And Secrets 🔐

- Do not commit `.env`.
- Prefer `uv run opensre onboard` or your OS keychain for provider keys.
- `.env.example` is the template for supported settings.
- Telemetry is opt-out and can be disabled:

```bash
export OPENSRE_NO_TELEMETRY=1
```

More detail: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#telemetry-and-privacy).

---

## Benchmarks 🧪

Run benchmark workflows:

```bash
make benchmark
```

Refresh README benchmark copy from cached results:

```bash
make benchmark-update-readme
```

<!-- BENCHMARK-START -->

_No benchmark results yet._

<!-- BENCHMARK-END -->

---

## License 📄

Apache 2.0. See [LICENSE](LICENSE).
