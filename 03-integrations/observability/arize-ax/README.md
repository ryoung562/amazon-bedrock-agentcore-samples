# Strands Agent with Arize AX Observability

This example shows how to instrument a [Strands](https://strandsagents.com/) agent with [Arize AX](https://arize.com/) observability using OpenTelemetry. The agent exposes weather, time, and calculator tools and sends full traces — including LLM calls, tool invocations, and token usage — to Arize AX for monitoring and debugging.

## Architecture

```
┌──────────────┐    OTLP/gRPC    ┌──────────┐
│ Strands Agent│───────────────►│ Arize AX │
│  (OTel SDK)  │                │ Platform │
└──────┬───────┘                └──────────┘
       │
       ├── get_weather (mock weather data)
       ├── get_time    (timezone lookup)
       └── calculator  (math operations)
```

Strands agents emit OpenTelemetry spans natively. A custom `StrandsToOpenInferenceProcessor` converts those spans to the [OpenInference](https://github.com/Arize-ai/openinference) semantic convention format that Arize expects, then exports them over gRPC to Arize's OTLP endpoint.

## Prerequisites

- Python 3.10+
- AWS credentials configured (`aws configure`) with Amazon Bedrock model access
- An [Arize AX](https://app.arize.com/) account — you will need your **API key** and **Space ID**
- Docker (only if deploying to AgentCore Runtime)

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Set Arize AX environment variables:

```bash
export ARIZE_API_KEY="your-arize-api-key"
export ARIZE_SPACE_ID="your-arize-space-id"
export ARIZE_ENDPOINT="https://otlp.arize.com:443"   # default
export ARIZE_PROJECT_NAME="strands-weather-agent"     # optional
```

3. Set AWS region and model (optional — defaults shown):

```bash
export AWS_DEFAULT_REGION="us-west-2"
export BEDROCK_MODEL_ID="us.anthropic.claude-haiku-4-5-20251001-v1:0"
```

## Usage

### Run locally

```bash
cd 03-integrations/observability/arize-ax
python -m agent.weather_time_agent
```

The agent starts an HTTP server on port 8080. Invoke it:

```bash
curl -X POST http://localhost:8080/invocations \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the weather in Tokyo and what time is it there?"}'
```

### Deploy to AgentCore Runtime

```python
from bedrock_agentcore_starter_toolkit import Runtime

runtime = Runtime()
runtime.configure(
    entrypoint="agent/weather_time_agent.py",
    requirements_file="requirements.txt",
    auto_create_execution_role=True,
    auto_create_ecr=True,
    memory_mode="NO_MEMORY",
    disable_otel=True,  # Disable default CloudWatch observability
)

headers = f"space_id={ARIZE_SPACE_ID},api_key={ARIZE_API_KEY}"
runtime.launch(
    env_vars={
        "OTEL_EXPORTER_OTLP_ENDPOINT": "https://otlp.arize.com:443",
        "OTEL_EXPORTER_OTLP_HEADERS": headers,
        "DISABLE_ADOT_OBSERVABILITY": "true",
    }
)
```

## Sample Prompts

- `"What's the weather in New York and London?"`
- `"What time is it in Tokyo right now?"`
- `"Calculate 15 factorial"`
- `"What's the weather in Paris and multiply 23 by 47"`

## Viewing Traces in Arize

1. Go to [app.arize.com](https://app.arize.com)
2. Navigate to your project (default: `strands-weather-agent`)
3. Click **Traces** to see agent invocations with:
   - Full agent execution flow (agent → cycle → LLM / tool)
   - LLM request/response payloads and token usage
   - Tool call parameters and outputs
   - Latency breakdown per span

## How It Works

The OpenTelemetry pipeline is set up in `agent/weather_time_agent.py`:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from strands_to_openinference_mapping import StrandsToOpenInferenceProcessor

provider = TracerProvider(resource=Resource.create({"model_id": "my-project"}))
provider.add_span_processor(StrandsToOpenInferenceProcessor())

exporter = OTLPSpanExporter(
    endpoint="https://otlp.arize.com:443",
    headers={"space_id": "...", "api_key": "..."},
)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider)
```

The `StrandsToOpenInferenceProcessor` converts Strands' native span attributes into the OpenInference format (span kinds like `LLM`, `TOOL`, `CHAIN`, `AGENT`; flattened message arrays; token counts; graph node hierarchy) so Arize can render rich trace visualizations.

## Clean Up

If deployed to AgentCore Runtime:

```python
import boto3

client = boto3.client("bedrock-agentcore-control")
client.delete_agent_runtime(agentRuntimeId="<your-agent-id>")
```
