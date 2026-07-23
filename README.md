# ADK Skeleton Agent Project

This repository contains a production-grade agent application built using the **Agent Development Kit (ADK)** Python framework.

## Project Structure

```
chore-planning-agent/
├── chore_planning_agent/  # Agent package directory
│   ├── tests/             # Golden test cases (JSON)
│   ├── agent.py           # Multi-agent definition and model routing
│   ├── logger.py          # Structured JSON logging and PII redaction
│   ├── memory.py          # Asynchronous memory compaction background task
│   └── tools.py           # Tools, Pydantic validators, OpenTelemetry spans
├── infra/                 # Infrastructure as Code (Terraform configs)
├── main.tf                # Root IaC config
├── variables.tf           # Root IaC variables
├── run_agent.py           # CLI runner (SQLite persistence, OTEL tracer, intent capture)
├── run_evaluation_suite.py# Automated CI/CD golden dataset evaluation script
└── README.md              # Documentation
```

---

## Getting Started

### 1. Prerequisites

- Python 3.10 or later.
- Google Cloud CLI (`gcloud`) installed and authorized.

### 2. Activate the Virtual Environment

```bash
source .venv/bin/activate
```

### 3. Configure local credentials

Run the following command to authenticate application credentials:

```bash
gcloud auth application-default login
```

---

## Agent CLI Usage

ADK provides built-in CLI commands to interact with, inspect, and test the agent.

### 1. Interactive Terminal Chat
To start an interactive chat session with the coordinator agent in the terminal:

```bash
adk run chore_planning_agent
```

### 2. Developer Web UI
To spin up a FastAPI-based browser testing UI for debugging tools and execution paths:

```bash
adk web .
```
Navigate to: **[http://localhost:8000](http://localhost:8000)** and select `chore_planning_agent` from the dropdown.

### 3. Fixture Replay & pytest Suite
To run pytest on the JSON test fixtures in the `tests/` directory:

```bash
adk test .
```

To update or rebuild the expected responses in the JSON test files using the live agent configuration:

```bash
adk test --rebuild .
```

---

## Multi-Agent Architecture & Routing

The project uses a structured multi-agent pattern with routing:
- **`chore_planning_agent`** (Coordinator): Routed to **`gemini-3.5-pro`** (large reasoning model) to handle context orchestration, policy guardrails, and session state.
- **`calendar_agent`** (Worker): Routed to **`gemini-3.5-flash`** (lightweight execution model) to handle calendar write actions.

---

## Safety Guardrails & Human-in-the-Loop

1. **Policy Verification Guardrail**: The coordinator executes the `verify_chore_policy` tool before saving or scheduling a chore to check for profanity, quiet hours violations (23:00 - 06:00), or duration limits (> 6 hours).
2. **Human-in-the-Loop (HITL) Gate**: Calendar write tools require confirmation (`require_confirmation=True`). The runner intercepts writes and requests user permission at the terminal (`y/n`) before executing the write.

---

## Observability & Privacy

1. **Structured JSON Logging**: Logs are written as single-line JSON items for easy parsing by centralized logging stacks (e.g. Cloud Logging, Datadog).
2. **PII and Secret Redaction**: The logger detects and redacts emails, phone numbers, and Google API OAuth access tokens (`ya29...`) recursively from messages and attributes.
3. **OpenTelemetry Distributed Tracing**: Tracer spans are exported to console during execution, capturing span scopes for user query turns and individual tool calls.

---

## Context, Memory & Persistence

1. **ACID Persistence**: Session history is persisted inside a robust SQLite relational database (`sessions.db`) instead of transient JSON files.
2. **Background Memory Consolidation**: To prevent UI blocking, memory compaction is offloaded to a background task using `asyncio.create_task` at the end of every turn, summarizing long histories using Gemini.

---

## Infrastructure & Production Best Practices

### 1. Secret Manager Injection
The agent has a secure, built-in REST API wrapper in [secrets.py](file:///Users/shaoyanl/chore-planning-agent/chore_planning_agent/secrets.py) that interfaces with Google Cloud Secret Manager using Application Default Credentials (ADC).
- At startup, the agent requests the payload of the secret named `gemini-api-key`.
- If Secret Manager is authorized, it injects the secret value into the active environment under `GOOGLE_API_KEY`.
- If Secret Manager is not configured or fails, it falls back gracefully to checking local environment variables and `chore_planning_agent/.env`.

### 2. Infrastructure as Code (IaC)
Terraform configuration files (`main.tf` and `variables.tf`) are present in the project root to provision Google Cloud project resources (Calendar API, Secret Manager, IAM roles/service accounts).
To initialize and check:

```bash
terraform init
terraform plan -var="project_id=YOUR_PROJECT_ID"
```

### 3. Automated CI/CD Evaluation Suite
To run the automated agent validation suite against the golden dataset, run:

```bash
python run_evaluation_suite.py
```
This runs the full multi-agent, validation, and confirmation lifecycle, asserting that all required security guardrails and tool loops are executed correctly.
