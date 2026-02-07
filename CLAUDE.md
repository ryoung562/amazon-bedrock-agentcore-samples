# CLAUDE.md

This file provides guidance for AI assistants working with the Amazon Bedrock AgentCore Samples repository.

## Repository Overview

This is a samples/examples repository for **Amazon Bedrock AgentCore** — an AWS service for deploying and operating AI agents securely at scale, framework-agnostic and model-agnostic. The repo contains tutorials, use cases, framework integrations, infrastructure-as-code templates, and full-stack blueprints.

**License:** Apache 2.0

## Repository Structure

```
01-tutorials/          # Jupyter notebook tutorials organized by AgentCore component
  01-AgentCore-runtime/    # Serverless agent deployment and hosting
  02-AgentCore-gateway/    # API/Lambda-to-MCP tool conversion
  03-AgentCore-identity/   # Identity and access management (Okta, Entra, Cognito)
  04-AgentCore-memory/     # Persistent memory (short-term, long-term)
  05-AgentCore-tools/      # Code Interpreter and Browser Tool
  06-AgentCore-observability/ # OpenTelemetry tracing and monitoring
  07-AgentCore-evaluations/   # Agent quality assessment
  08-AgentCore-policy/     # Cedar-based policy enforcement
  09-AgentCore-E2E/        # End-to-end production migration

02-use-cases/          # 22+ complete end-to-end applications (community contributions go here)
03-integrations/       # Framework integrations (Strands, LangChain, CrewAI, LlamaIndex, etc.)
04-infrastructure-as-code/ # CloudFormation, CDK, and Terraform templates
05-blueprints/         # Full-stack reference applications with frontend + backend
```

## Languages and Build Systems

- **Primary language:** Python 3.10+ (~80% of codebase)
- **Secondary:** JavaScript/TypeScript (~12%), Java (~2%), HCL/Terraform (~3%)
- **Python package manager:** `uv` (preferred), `pip` (fallback)
- **Node.js version:** 18
- **Java build:** Maven (`pom.xml`)
- **Infrastructure:** CloudFormation (YAML), AWS CDK (Python), Terraform (HCL)
- **Containerization:** Docker (35+ Dockerfiles across the repo)

## Linting and Formatting

### Python

CI runs on PRs to `main` via `.github/workflows/python-lint.yml`:

```bash
# Lint check (ruff with default config — no ruff.toml or pyproject.toml config at root)
ruff check <files>

# Format check
ruff format --check <files>
```

Always run `ruff check` and `ruff format` on any modified Python files before committing. There is no root-level ruff configuration file; ruff uses its defaults.

### JavaScript/TypeScript

CI runs on PRs to `main` via `.github/workflows/js-lint.yml`:

```bash
# Lint
npx eslint <file>

# Format check
npx prettier --check <file>
```

Note: JS/TS lint steps use `continue-on-error: true` so failures are non-blocking.

## Testing

Tests are sparse across the repo (this is a samples repository, not a library). Where they exist:

```bash
# Standard pytest
pytest tests/

# Some projects use Makefiles
make test    # (e.g., 02-use-cases/SRE-agent/)

# UV-based
uv run pytest
```

Test files are found in select projects:
- `04-infrastructure-as-code/terraform/*/test_*.py`
- `02-use-cases/device-management-agent/device-management/test_lambda.py`
- `03-integrations/observability/simple-dual-observability/scripts/tests/`

## Running Notebooks

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name=notebook-venv --display-name="Python (notebook-venv)"
jupyter notebook path/to/notebook.ipynb
```

Root `requirements.txt` includes: `strands-agents`, `boto3`, `langchain`, `langgraph`, `bedrock-agentcore`, `mcp>=1.9.0`, `jupyterlab`, and related packages.

## Key Dependencies and Frameworks

- **Agent frameworks:** Strands Agents, LangChain/LangGraph, CrewAI, LlamaIndex, OpenAI Agents, Google ADK, PydanticAI, Mastra (TS)
- **AWS SDKs:** `boto3`, `bedrock-agentcore`, `bedrock-agentcore-starter-toolkit`
- **Protocols:** MCP (Model Context Protocol), A2A (Agent-to-Agent)
- **Observability:** OpenTelemetry, CloudWatch, Dynatrace, Langfuse, Braintrust, OpenLIT
- **Auth:** OAuth 2.0, Cognito, Okta, EntraID
- **Frontend:** React, Streamlit, AWS Amplify

## Common Patterns in the Codebase

### Agent Entrypoint Pattern (Strands + AgentCore Runtime)

```python
from bedrock_agentcore import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()
agent = Agent()

@app.entrypoint
async def invoke(payload, context):
    user_message = payload.get("prompt", "Hello!")
    result = agent(user_message)
    return {"result": result.message}
```

### Streaming Pattern

```python
@app.entrypoint
async def invoke(payload, context):
    async for chunk in agent.stream_async(user_query):
        yield chunk
```

### MCP Client Pattern

```python
from mcp.client.streamable_http import streamablehttp_client
gateway_client = MCPClient(lambda: streamablehttp_client(url=gateway_url))
```

### Dockerfile Pattern

Most agent Dockerfiles follow:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "main.py"]
```

## CI/CD Workflows

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| Python lint | `python-lint.yml` | PR to main | `ruff check` + `ruff format --check` |
| JS/TS lint | `js-lint.yml` | PR to main | ESLint + Prettier (non-blocking) |
| CodeQL | `codeql.yml` | Push | Security scanning |
| ASH scan | `ash-security-scan.yml` | PR | AWS security scanning |
| Dependabot | `dependabot.yml` | PR (bot) | Dependency update metadata |

## Contribution Guidelines

- **Tutorials (`01-tutorials/`)**: AWS-maintained; only submit here for core functionality tutorials.
- **Use cases (`02-use-cases/`)**: Primary target for community contributions.
- **Integrations (`03-integrations/`)**: For framework integration examples.
- PRs follow an **issue-first approach** — open an issue before submitting a PR.
- Attach the `review ready` label when the PR is ready for review.
- PR checklist requires: Introduction, Architecture Diagram, Prerequisites, Usage, Sample Prompts, and Clean Up steps in the README.

## Working with This Repo

- Each sample is self-contained with its own `requirements.txt` or `pyproject.toml`.
- Many samples require AWS credentials configured (`aws configure`) and specific IAM permissions.
- Model access (e.g., Claude on Bedrock) must be enabled in the AWS console.
- Docker or Finch is required for local agent development and testing.
- Environment variables are documented in `.env.example` files within individual projects.
- Do not commit `.env` files, credentials, or AWS configuration secrets.
