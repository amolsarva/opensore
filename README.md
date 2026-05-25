<div align="center">

<p align="center">
  <img src="docs/logo/opensore-logo-white.svg" alt="OpenSore" width="360" />
</p>

# OpenSore 🕵️‍♀️

### AI-assisted incident investigation for lawyers, HR, boards, and compliance teams.

[![Status](https://img.shields.io/badge/status-investigation%20alpha-orange?style=for-the-badge)](#)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue?style=for-the-badge)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache%202.0-green?style=for-the-badge)](LICENSE)
[![Repo](https://img.shields.io/badge/github-amolsarva%2Fopensore-black?style=for-the-badge&logo=github)](https://github.com/amolsarva/opensore)

</div>

---

## What Is This? ⚖️

OpenSore is an AI-assisted investigation workspace for high-stakes workplace incidents: sexual harassment, retaliation, discrimination, executive misconduct, policy violations, conflicts of interest, and board-level crises.

It helps investigation teams collect scattered evidence, organize it into a defensible timeline, surface contradictions, and draft structured incident reports. The project is built on OpenSore's agentic investigation engine, but the product direction is now focused on **legal, HR, compliance, and workplace misconduct investigations** rather than infrastructure outages.

Use it when an organization needs to answer questions like:

- 🧑‍⚖️ What happened, when, and who knew?
- 📬 Which emails, chats, documents, and calendar events matter?
- 🧾 What evidence supports or contradicts each allegation?
- 🧑‍💼 Were executives, managers, HR, or legal notified?
- ⏱️ Did retaliation, escalation, or cover-up behavior appear after a complaint?
- 📁 What should counsel or HR review next?

> OpenSore is not legal advice and does not replace counsel, HR judgment, or a licensed investigator. It is a tool for evidence organization, analysis, and report drafting.

---

## Who It Is For 👥

| Role | What OpenSore Helps With |
| --- | --- |
| ⚖️ Employment lawyers | Build timelines, summarize evidence, find gaps, prepare matter memos |
| 🧑‍💼 HR / People teams | Triage complaints, organize interviews, document follow-up actions |
| 🏛️ Boards / special committees | Investigate executive incidents with source-backed summaries |
| 🕵️ Outside investigators | Pull together documents, messages, calendars, and witness notes |
| ✅ Compliance teams | Review policy violations, escalation paths, and repeated conduct patterns |
| 🧑‍💻 Technical operators | Connect local files, SaaS exports, and internal systems into one workflow |

---

## What It Does 🔎

OpenSore turns messy workplace evidence into an investigation file.

- 📥 **Ingests evidence** from local files, exports, email archives, docs, chats, calendars, tickets, and connected tools.
- 🧭 **Builds timelines** across people, dates, systems, and allegations.
- 🧠 **Uses LLMs carefully** to summarize, classify, and reason over evidence while keeping source references visible.
- 🧾 **Drafts investigation reports** with allegations, facts, chronology, confidence, open questions, and next steps.
- 🧩 **Finds contradictions and gaps** such as missing follow-ups, inconsistent accounts, unreviewed custodians, or suspicious timing.
- 🔐 **Keeps sensitive material local by default** when run from your machine.
- 🧪 **Supports repeatable test scenarios** so workflows can be validated before use on real matters.

---

## Example Investigation Scenarios 🚨

OpenSore is being shaped around incidents like:

- Sexual harassment complaint involving an executive and multiple witnesses
- Retaliation after a protected complaint or whistleblower report
- Board investigation into founder or C-suite misconduct
- HR failure-to-escalate review after repeated complaints
- Policy violation involving Slack, email, calendar, and document evidence
- Litigation hold review across user-owned exports
- Workplace culture investigation with many small signals spread across systems

The goal is not to magically decide the truth. The goal is to make the evidence review faster, more complete, and more auditable.

---

## Quickstart ⚡

Clone and install:

```bash
cd ~/Documents/root/opensore
brew install uv          # macOS, if uv is not installed
make install
```

Always run this checkout with `uv run`:

```bash
uv run opensore --help
uv run opensore doctor
```

Configure an LLM provider:

```bash
uv run opensore onboard
```

Or create a minimal local `.env`:

```bash
LLM_PROVIDER=openai
OPENAI_REASONING_MODEL=gpt-5.4-mini
OPENAI_TOOLCALL_MODEL=gpt-5.4-mini
AWS_PROFILE=amol
AWS_REGION=us-east-1
```

Store API keys in your shell, macOS Keychain, or the OpenSore onboarding flow. Do not commit `.env` files with secrets.

Run the local app:

```bash
uv run uvicorn app.webapp:app --reload --host 127.0.0.1 --port 8000
```

Then open:

```text
http://127.0.0.1:8000
```

Healthy local configuration:

```json
{"ok":true,"version":"0.1","llm_configured":true,"env":"development"}
```

---

## Run Modes 🛠️

### 1. Interactive Investigation Shell

Use the terminal REPL to describe an incident, ask questions, inspect evidence, and run investigation commands:

```bash
uv run opensore
```

Useful commands:

```text
/help
/doctor
/status
/trust on
/effort high
/exit
```

### 2. One-Shot Evidence Review

Run an investigation against a structured alert or evidence payload:

```bash
uv run opensore investigate -i tests/e2e/kubernetes/fixtures/datadog_k8s_alert.json
```

The historical fixture above is infrastructure-shaped because this project started from OpenSore. New workplace-focused fixtures and workflows live under the workplace discovery docs and are being expanded.

### 3. Local Web App

Run the FastAPI service for local UI/API workflows:

```bash
uv run uvicorn app.webapp:app --reload --host 127.0.0.1 --port 8000
```

### 4. Workplace Discovery Direction

Start with the product plan:

[docs/workplace-discovery-product-plan.mdx](docs/workplace-discovery-product-plan.mdx)

The intended hosted mode avoids storing user evidence on the OpenSore host. Users authenticate their own source accounts, and exports should be written to user-owned storage such as Google Drive.

Run deterministic local discovery over exported workplace data:

```bash
uv run opensore discovery plan matter.json
uv run opensore discovery run matter.json --source slack-export.csv --source gmail-export.json --out ./matter-output
```

This writes `discovery_evidence.csv`, `discovery_hit_report.csv`, and `discovery_manifest.json`
for counsel, HR, compliance, or an investigator to review. See
[docs/discovery-cli.mdx](docs/discovery-cli.mdx).

### 5. Native Desktop Case Desk

The Electron desktop shell gives lawyers, HR, boards, and investigators a native matter workspace on top of the same discovery engine:

```bash
npm install
npm run desktop
```

Use it to define a matter, add custodians, choose local evidence exports, tune keyword sets, preview the discovery plan, run local export search, and review the generated CSV artifacts. See [docs/desktop-case-desk.mdx](docs/desktop-case-desk.mdx).

### 6. Personal Agent And Messaging

For local assistant workflows, WhatsApp experiments, and OpenClaw-style local automation:

```bash
uv run opensore personal doctor
uv run opensore integrations setup whatsapp
uv run opensore messaging pair --platform whatsapp
```

See [docs/macos-personal-agent-quickstart.mdx](docs/macos-personal-agent-quickstart.mdx) and [docs/personal-agent-roadmap.mdx](docs/personal-agent-roadmap.mdx).

---

## How An Investigation Works 🧭

OpenSore follows an evidence-first loop:

1. 📥 **Intake**: describe the incident, upload/export evidence, or point the tool at connected systems.
2. 🗂️ **Normalize**: convert messages, docs, calendar items, tickets, and notes into reviewable records.
3. 🧑‍🤝‍🧑 **Map actors**: identify complainants, respondents, witnesses, HR/legal contacts, managers, and executives.
4. ⏱️ **Build chronology**: order events, communications, meetings, escalations, and follow-up actions.
5. 🧠 **Analyze**: summarize allegations, evidence, contradictions, corroboration, and missing records.
6. 🧾 **Draft report**: produce a source-backed investigation memo with findings, confidence, gaps, and next steps.
7. 🔁 **Iterate**: add custodians, refine date ranges, compare witness accounts, and rerun targeted review.

For deeper technical internals, see [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md), [docs/routing-policy-architecture.md](docs/routing-policy-architecture.md), and [docs/investigation-tool-calling.md](docs/investigation-tool-calling.md).

---

## Evidence Sources And Integrations 🔌

OpenSore can reuse OpenSore's broad integration layer, but the investigation story is about workplace evidence rather than server telemetry.

| Evidence Area | Examples |
| --- | --- |
| 📧 Communications | Gmail exports, Slack, Discord, Telegram, WhatsApp experiments, chat transcripts |
| 📄 Documents | Google Docs, Drive exports, PDFs, Markdown notes, local files |
| 📆 Calendar | Meetings, invites, attendee lists, timing around complaints or escalation |
| 🧾 HR / Legal records | Complaint notes, policy documents, interview summaries, matter memos |
| 🧑‍💻 Workplace systems | GitHub, Jira, GitLab, tickets, access logs, internal tool exports |
| ☁️ Cloud / storage | AWS, Google Drive, local folders, user-owned export destinations |
| 🤖 LLMs | OpenAI, Anthropic, OpenRouter, Gemini, Bedrock, Ollama, Codex CLI, Claude Code |

Set up integrations with:

```bash
uv run opensore integrations setup <service>
uv run opensore integrations verify <service>
```

List available integration commands:

```bash
uv run opensore integrations --help
```

---

## Privacy, Privilege, And Evidence Handling 🔐

This project deals with sensitive workplace allegations and potentially privileged material. Treat every real investigation as confidential.

- Do not commit `.env`, evidence exports, interview notes, or matter files.
- Prefer OS keychain storage for LLM and integration credentials.
- Keep raw evidence in user-owned storage whenever possible.
- Use read-only credentials for source systems.
- Keep source references attached to summaries so reviewers can inspect the underlying record.
- Disable telemetry for sensitive work:

```bash
export OPENSORE_NO_TELEMETRY=1
```

Telemetry details: [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#telemetry-and-privacy).

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
| `app/` | CLI, agent logic, investigation pipeline, integrations, tools, state, and web app |
| `desktop/` | Electron Case Desk for native legal/HR discovery workflows |
| `tests/` | Unit, integration, synthetic, e2e, deployment, and scenario tests |
| `docs/` | Product plans, investigation docs, integration guides, and contributor notes |
| `.github/` | Workflows, templates, and repo automation |
| `pyproject.toml` | Python package metadata and dependency config |
| `Makefile` | Canonical local commands |
| `SETUP.md` | Local setup and troubleshooting |
| `CI.md` | Required push/PR readiness checklist |

---

## Key Docs 📚

- [docs/workplace-discovery-product-plan.mdx](docs/workplace-discovery-product-plan.mdx) - primary product direction for workplace investigations
- [docs/macos-personal-agent-quickstart.mdx](docs/macos-personal-agent-quickstart.mdx) - Mac personal-agent path
- [docs/personal-agent-roadmap.mdx](docs/personal-agent-roadmap.mdx) - personal-agent roadmap
- [SETUP.md](SETUP.md) - install, uv, Windows, troubleshooting, OpenClaw setup
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) - contributor workflow, benchmarks, deployment, telemetry
- [CI.md](CI.md) - mandatory checks before push or PR
- [CONTRIBUTING.md](CONTRIBUTING.md) - contribution workflow
- [SECURITY.md](SECURITY.md) - security policy

---

## Deployment 🚢

OpenSore can run as a local-only tool or as a hosted FastAPI service. For legal and HR matters, default to local or user-owned storage until the evidence-handling model is explicitly reviewed.

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

For hosted deployments, review privilege, retention, access controls, audit logging, and data residency before connecting real evidence. If persistence is needed, configure storage such as `DATABASE_URI` and `REDIS_URI`. See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#deployment).

---

## Built On OpenSore 🧬

This repository began as an OpenSore fork for AI site-reliability investigations. Much of the lower-level agent, CLI, integration, and test infrastructure still reflects that origin.

The repositioning is deliberate:

- From server outages ➜ workplace incidents
- From logs and traces ➜ communications, documents, calendars, and HR records
- From root-cause analysis ➜ source-backed investigation memos
- From SRE operators ➜ lawyers, HR, boards, compliance, and outside investigators

Some older infrastructure-oriented fixtures and docs remain while the workplace investigation workflows are expanded.

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
