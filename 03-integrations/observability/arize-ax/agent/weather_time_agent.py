"""Strands agent with Arize AX observability via OpenTelemetry.

This agent demonstrates weather, time, and calculator tools with full
trace export to Arize AX using the OpenInference span format.

It can run locally (``python -m agent.weather_time_agent``) or be deployed
to Amazon Bedrock AgentCore Runtime.

Required environment variables for Arize AX:
    ARIZE_API_KEY   – Your Arize API key
    ARIZE_SPACE_ID  – Your Arize space identifier
    ARIZE_ENDPOINT  – Arize OTLP endpoint (default: https://otlp.arize.com:443)
"""

import logging
import os
from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from strands import Agent, tool
from strands.models import BedrockModel

from strands_to_openinference_mapping import StrandsToOpenInferenceProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# OpenTelemetry → Arize AX setup
# ------------------------------------------------------------------

ARIZE_API_KEY = os.getenv("ARIZE_API_KEY", "")
ARIZE_SPACE_ID = os.getenv("ARIZE_SPACE_ID", "")
ARIZE_ENDPOINT = os.getenv("ARIZE_ENDPOINT", "https://otlp.arize.com:443")
ARIZE_PROJECT_NAME = os.getenv("ARIZE_PROJECT_NAME", "strands-weather-agent")


def _setup_arize_telemetry() -> None:
    """Configure OpenTelemetry to export Strands traces to Arize AX."""
    if not ARIZE_API_KEY or not ARIZE_SPACE_ID:
        logger.warning(
            "ARIZE_API_KEY or ARIZE_SPACE_ID not set — traces will NOT be exported"
        )
        return

    resource = Resource.create({"model_id": ARIZE_PROJECT_NAME})
    provider = TracerProvider(resource=resource)

    # Processor that converts Strands span attributes → OpenInference format
    provider.add_span_processor(StrandsToOpenInferenceProcessor())

    # OTLP gRPC exporter authenticated with Arize headers
    headers = f"space_id={ARIZE_SPACE_ID},api_key={ARIZE_API_KEY}"
    exporter = OTLPSpanExporter(
        endpoint=ARIZE_ENDPOINT,
        headers=dict(item.split("=", 1) for item in headers.split(",")),
    )
    provider.add_span_processor(BatchSpanProcessor(exporter))

    trace.set_tracer_provider(provider)
    logger.info("Arize AX telemetry configured (endpoint=%s)", ARIZE_ENDPOINT)


_setup_arize_telemetry()

# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------


@tool
def get_weather(city: str) -> dict[str, Any]:
    """Get current weather information for a city.

    Args:
        city: The city name (e.g., 'Seattle', 'New York')

    Returns:
        Weather information including temperature, conditions, and humidity
    """
    from tools.weather_tool import get_weather as _impl

    logger.info("Getting weather for: %s", city)
    return _impl(city)


@tool
def get_time(timezone: str) -> dict[str, Any]:
    """Get current time for a timezone.

    Args:
        timezone: Timezone name (e.g., 'America/New_York', 'Europe/London')

    Returns:
        Current time, date, timezone, and UTC offset information
    """
    from tools.time_tool import get_time as _impl

    logger.info("Getting time for: %s", timezone)
    return _impl(timezone)


@tool
def calculator(operation: str, a: float, b: float = None) -> dict[str, Any]:
    """Perform mathematical calculations.

    Args:
        operation: The operation (add, subtract, multiply, divide, factorial)
        a: First number (or the number for factorial)
        b: Second number (not used for factorial)

    Returns:
        Calculation result with operation details
    """
    from tools.calculator_tool import calculator as _impl

    logger.info("Calculating: %s(%s, %s)", operation, a, b)
    return _impl(operation, a, b)


# ------------------------------------------------------------------
# Agent & entrypoint
# ------------------------------------------------------------------

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
model = BedrockModel(
    model_id=MODEL_ID,
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-west-2"),
)

SYSTEM_PROMPT = (
    "You are a helpful assistant with access to weather, time, and calculator tools. "
    "Use these tools to accurately answer user questions. Always provide clear, "
    "concise responses based on the tool outputs. When using tools:\n"
    "- For weather: Use the city name directly\n"
    "- For time: Use timezone format like 'America/New_York' or city names\n"
    "- For calculator: Use operations like 'add', 'subtract', 'multiply', "
    "'divide', or 'factorial'\n"
    "Be friendly and helpful in your responses."
)

app = BedrockAgentCoreApp()


def _create_agent() -> Agent:
    return Agent(
        model=model,
        tools=[get_weather, get_time, calculator],
        system_prompt=SYSTEM_PROMPT,
    )


@app.entrypoint
def invoke(payload: dict[str, Any]) -> str:
    """AgentCore Runtime entrypoint.

    Args:
        payload: Input payload with a ``prompt`` key.

    Returns:
        Agent response text.
    """
    user_input = payload.get("prompt", "")
    logger.info("Agent invoked with prompt: %s", user_input)

    agent = _create_agent()
    response = agent(user_input)
    response_text = response.message["content"][0]["text"]

    logger.info("Agent invocation completed")
    return response_text


if __name__ == "__main__":
    app.run()
