"""Strands-to-OpenInference span processor for Arize AX.

Converts Strands telemetry spans into the OpenInference semantic convention
format expected by Arize AX for rich trace visualization.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from opentelemetry.sdk.trace import SpanProcessor
from opentelemetry.trace import Span

logger = logging.getLogger(__name__)


class StrandsToOpenInferenceProcessor(SpanProcessor):
    """SpanProcessor that converts Strands OTel attributes to OpenInference format."""

    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.processed_spans: set[int] = set()
        self.span_hierarchy: dict[int, dict[str, Any]] = {}

    def on_start(self, span, parent_context=None):
        span_id = span.get_span_context().span_id
        parent_id = None
        if parent_context and hasattr(parent_context, "span_id"):
            parent_id = parent_context.span_id
        elif span.parent and hasattr(span.parent, "span_id"):
            parent_id = span.parent.span_id

        self.span_hierarchy[span_id] = {
            "name": span.name,
            "span_id": span_id,
            "parent_id": parent_id,
            "start_time": datetime.now().isoformat(),
        }

    def on_end(self, span: Span):
        if not hasattr(span, "_attributes") or not span._attributes:
            return

        original_attrs = dict(span._attributes)
        span_id = span.get_span_context().span_id

        if span_id in self.span_hierarchy:
            self.span_hierarchy[span_id]["attributes"] = original_attrs

        try:
            events = []
            if hasattr(span, "_events"):
                events = span._events
            elif hasattr(span, "events"):
                events = span.events

            transformed = self._transform_attributes(original_attrs, span, events)
            span._attributes.clear()
            span._attributes.update(transformed)
            self.processed_spans.add(span_id)

            if self.debug:
                logger.info(
                    "Transformed span '%s': %d -> %d attributes",
                    span.name,
                    len(original_attrs),
                    len(transformed),
                )
        except Exception:
            logger.exception("Failed to transform span '%s'", span.name)
            span._attributes.clear()
            span._attributes.update(original_attrs)

    # ------------------------------------------------------------------
    # Core transformation
    # ------------------------------------------------------------------

    def _transform_attributes(
        self, attrs: dict[str, Any], span: Span, events: list
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        span_kind = self._determine_span_kind(span, attrs)
        result["openinference.span.kind"] = span_kind
        self._set_graph_node_attributes(span, attrs, result)

        if events:
            input_msgs, output_msgs = self._extract_messages_from_events(events)
        else:
            prompt = attrs.get("gen_ai.prompt")
            completion = attrs.get("gen_ai.completion")
            if prompt or completion:
                input_msgs, output_msgs = self._extract_messages_from_attributes(
                    prompt, completion
                )
            else:
                input_msgs, output_msgs = [], []

        model_id = attrs.get("gen_ai.request.model")
        agent_name = attrs.get("agent.name") or attrs.get("gen_ai.agent.name")

        if model_id:
            result["llm.model_name"] = model_id
            result["gen_ai.request.model"] = model_id
        if agent_name:
            result["llm.system"] = "strands-agents"
            result["llm.provider"] = "strands-agents"

        self._handle_tags(attrs, result)

        if span_kind in ("LLM", "AGENT", "CHAIN"):
            self._handle_llm_span(attrs, result, input_msgs, output_msgs)
        elif span_kind == "TOOL":
            self._handle_tool_span(attrs, result, events)

        self._map_token_usage(attrs, result)

        for key in (
            "session.id",
            "user.id",
            "llm.prompt_template.template",
            "llm.prompt_template.version",
            "llm.prompt_template.variables",
        ):
            if key in attrs:
                result[key] = attrs[key]

        self._add_metadata(attrs, result)
        return result

    # ------------------------------------------------------------------
    # Span kind detection
    # ------------------------------------------------------------------

    def _determine_span_kind(self, span: Span, attrs: dict[str, Any]) -> str:
        name = span.name
        if name == "chat":
            return "LLM"
        if name.startswith("execute_tool "):
            return "TOOL"
        if name == "execute_event_loop_cycle":
            return "CHAIN"
        if name.startswith("invoke_agent"):
            return "AGENT"
        # Legacy naming
        if "Model invoke" in name:
            return "LLM"
        if name.startswith("Tool:"):
            return "TOOL"
        if "Cycle" in name:
            return "CHAIN"
        if attrs.get("gen_ai.agent.name") or attrs.get("agent.name"):
            return "AGENT"
        return "CHAIN"

    # ------------------------------------------------------------------
    # Graph node hierarchy (for Arize trace view)
    # ------------------------------------------------------------------

    def _set_graph_node_attributes(
        self, span: Span, attrs: dict[str, Any], result: dict[str, Any]
    ):
        span_kind = result["openinference.span.kind"]
        span_id = span.get_span_context().span_id
        span_info = self.span_hierarchy.get(span_id, {})
        parent_id = span_info.get("parent_id")
        parent_info = self.span_hierarchy.get(parent_id, {}) if parent_id else {}
        parent_name = parent_info.get("name", "")

        if span_kind == "AGENT":
            result["graph.node.id"] = "strands_agent"
        elif span_kind == "CHAIN":
            cycle_id = attrs.get("event_loop.cycle_id", f"cycle_{span_id}")
            result["graph.node.id"] = f"cycle_{cycle_id}"
            result["graph.node.parent_id"] = "strands_agent"
        elif span_kind == "LLM":
            result["graph.node.id"] = f"llm_{span_id}"
            parent_cycle_id = parent_info.get("attributes", {}).get(
                "event_loop.cycle_id"
            )
            if parent_cycle_id and (
                parent_name == "execute_event_loop_cycle"
                or parent_name.startswith("Cycle")
            ):
                result["graph.node.parent_id"] = f"cycle_{parent_cycle_id}"
            else:
                result["graph.node.parent_id"] = "strands_agent"
        elif span_kind == "TOOL":
            tool_name = (
                span.name.replace("execute_tool ", "")
                if span.name.startswith("execute_tool ")
                else "unknown_tool"
            )
            result["graph.node.id"] = f"tool_{tool_name}_{span_id}"
            parent_cycle_id = parent_info.get("attributes", {}).get(
                "event_loop.cycle_id"
            )
            if parent_cycle_id and (
                parent_name == "execute_event_loop_cycle"
                or parent_name.startswith("Cycle")
            ):
                result["graph.node.parent_id"] = f"cycle_{parent_cycle_id}"
            else:
                result["graph.node.parent_id"] = "strands_agent"

    # ------------------------------------------------------------------
    # Message extraction from OTel events
    # ------------------------------------------------------------------

    def _extract_messages_from_events(
        self, events: list
    ) -> tuple[list[dict], list[dict]]:
        input_messages: list[dict] = []
        output_messages: list[dict] = []

        for event in events:
            name = (
                getattr(event, "name", "")
                if hasattr(event, "name")
                else event.get("name", "")
            )
            ea = (
                getattr(event, "attributes", {})
                if hasattr(event, "attributes")
                else event.get("attributes", {})
            )

            if name == "gen_ai.user.message":
                msg = self._parse_message_content(ea.get("content", ""), "user")
                if msg:
                    input_messages.append(msg)
            elif name == "gen_ai.assistant.message":
                msg = self._parse_message_content(ea.get("content", ""), "assistant")
                if msg:
                    output_messages.append(msg)
            elif name == "gen_ai.choice":
                msg = self._parse_message_content(ea.get("message", ""), "assistant")
                if msg:
                    if "finish_reason" in ea:
                        msg["message.finish_reason"] = ea["finish_reason"]
                    output_messages.append(msg)
            elif name == "gen_ai.tool.message":
                content = ea.get("content", "")
                tool_id = ea.get("id", "")
                if content:
                    msg = self._parse_message_content(content, "tool")
                    if msg and tool_id:
                        msg["message.tool_call_id"] = tool_id
                        input_messages.append(msg)

        return input_messages, output_messages

    def _extract_messages_from_attributes(
        self, prompt: Any, completion: Any
    ) -> tuple[list[dict], list[dict]]:
        input_messages: list[dict] = []
        output_messages: list[dict] = []

        if prompt:
            if isinstance(prompt, str):
                try:
                    prompt_data = json.loads(prompt)
                    if isinstance(prompt_data, list):
                        for msg in prompt_data:
                            normalized = self._normalize_message(msg)
                            if normalized.get("message.role") == "user":
                                input_messages.append(normalized)
                except json.JSONDecodeError:
                    input_messages.append(
                        {"message.role": "user", "message.content": str(prompt)}
                    )

        if completion:
            if isinstance(completion, str):
                try:
                    completion_data = json.loads(completion)
                    if isinstance(completion_data, list):
                        msg = self._parse_strands_completion(completion_data)
                        if msg:
                            output_messages.append(msg)
                except json.JSONDecodeError:
                    output_messages.append(
                        {
                            "message.role": "assistant",
                            "message.content": str(completion),
                        }
                    )

        return input_messages, output_messages

    # ------------------------------------------------------------------
    # Message content parsing
    # ------------------------------------------------------------------

    def _parse_message_content(self, content: str, role: str) -> Optional[dict]:
        if not content:
            return None
        try:
            data = json.loads(content) if isinstance(content, str) else content
            if isinstance(data, list):
                message: dict[str, Any] = {
                    "message.role": role,
                    "message.content": "",
                    "message.tool_calls": [],
                }
                text_parts: list[str] = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    if "text" in item:
                        text_parts.append(str(item["text"]))
                    elif "toolUse" in item:
                        tu = item["toolUse"]
                        message["message.tool_calls"].append(
                            {
                                "tool_call.id": tu.get("toolUseId", ""),
                                "tool_call.function.name": tu.get("name", ""),
                                "tool_call.function.arguments": json.dumps(
                                    tu.get("input", {})
                                ),
                            }
                        )
                    elif "toolResult" in item:
                        tr = item["toolResult"]
                        if "content" in tr:
                            if isinstance(tr["content"], list):
                                for c in tr["content"]:
                                    if isinstance(c, dict) and "text" in c:
                                        text_parts.append(str(c["text"]))
                            elif isinstance(tr["content"], str):
                                text_parts.append(tr["content"])
                        message["message.role"] = "tool"
                        if "toolUseId" in tr:
                            message["message.tool_call_id"] = tr["toolUseId"]
                message["message.content"] = " ".join(text_parts) if text_parts else ""
                if not message["message.tool_calls"]:
                    del message["message.tool_calls"]
                return message
            if isinstance(data, dict):
                return {
                    "message.role": role,
                    "message.content": str(data.get("text", data)),
                }
            return {"message.role": role, "message.content": str(data)}
        except (json.JSONDecodeError, TypeError):
            return {"message.role": role, "message.content": str(content)}

    def _parse_strands_completion(self, completion_data: list) -> Optional[dict]:
        message: dict[str, Any] = {
            "message.role": "assistant",
            "message.content": "",
            "message.tool_calls": [],
        }
        text_parts: list[str] = []
        for item in completion_data:
            if not isinstance(item, dict):
                continue
            if "text" in item:
                text_parts.append(str(item["text"]))
            elif "toolUse" in item:
                tu = item["toolUse"]
                message["message.tool_calls"].append(
                    {
                        "tool_call.id": tu.get("toolUseId", ""),
                        "tool_call.function.name": tu.get("name", ""),
                        "tool_call.function.arguments": json.dumps(tu.get("input", {})),
                    }
                )
        message["message.content"] = " ".join(text_parts) if text_parts else ""
        if not message["message.tool_calls"]:
            del message["message.tool_calls"]
        return (
            message
            if message["message.content"] or "message.tool_calls" in message
            else None
        )

    # ------------------------------------------------------------------
    # LLM / Tool span handlers
    # ------------------------------------------------------------------

    def _handle_llm_span(
        self,
        attrs: dict[str, Any],
        result: dict[str, Any],
        input_messages: list[dict],
        output_messages: list[dict],
    ):
        if input_messages:
            result["llm.input_messages"] = json.dumps(
                input_messages, separators=(",", ":")
            )
            self._flatten_messages(input_messages, "llm.input_messages", result)
        if output_messages:
            result["llm.output_messages"] = json.dumps(
                output_messages, separators=(",", ":")
            )
            self._flatten_messages(output_messages, "llm.output_messages", result)

        if tools := (attrs.get("gen_ai.agent.tools") or attrs.get("agent.tools")):
            self._map_tools(tools, result)

        self._create_input_output_values(attrs, result, input_messages, output_messages)
        self._map_invocation_parameters(attrs, result)

    def _handle_tool_span(
        self, attrs: dict[str, Any], result: dict[str, Any], events: list
    ):
        tool_name = attrs.get("gen_ai.tool.name")
        tool_call_id = attrs.get("gen_ai.tool.call.id")
        tool_status = attrs.get("tool.status")

        if tool_name:
            result["tool.name"] = tool_name
        if tool_call_id:
            result["tool.call_id"] = tool_call_id
        if tool_status:
            result["tool.status"] = tool_status

        if not events:
            return

        tool_parameters = None
        tool_output = None

        for event in events:
            ename = (
                getattr(event, "name", "")
                if hasattr(event, "name")
                else event.get("name", "")
            )
            ea = (
                getattr(event, "attributes", {})
                if hasattr(event, "attributes")
                else event.get("attributes", {})
            )

            if ename == "gen_ai.tool.message":
                content = ea.get("content", "")
                if content:
                    try:
                        cd = (
                            json.loads(content) if isinstance(content, str) else content
                        )
                        tool_parameters = (
                            cd if isinstance(cd, dict) else {"input": str(cd)}
                        )
                    except (json.JSONDecodeError, TypeError):
                        tool_parameters = {"input": str(content)}
            elif ename == "gen_ai.choice":
                message = ea.get("message", "")
                if message:
                    try:
                        md = (
                            json.loads(message) if isinstance(message, str) else message
                        )
                        if isinstance(md, list):
                            parts = [
                                item["text"]
                                for item in md
                                if isinstance(item, dict) and "text" in item
                            ]
                            tool_output = " ".join(parts) if parts else str(md)
                        else:
                            tool_output = str(md)
                    except (json.JSONDecodeError, TypeError):
                        tool_output = str(message)

        if tool_parameters:
            result["tool.parameters"] = json.dumps(
                tool_parameters, separators=(",", ":")
            )
            if tool_name and tool_call_id:
                input_msgs = [
                    {
                        "message.role": "assistant",
                        "message.content": "",
                        "message.tool_calls": [
                            {
                                "tool_call.id": tool_call_id,
                                "tool_call.function.name": tool_name,
                                "tool_call.function.arguments": json.dumps(
                                    tool_parameters, separators=(",", ":")
                                ),
                            }
                        ],
                    }
                ]
                result["llm.input_messages"] = json.dumps(
                    input_msgs, separators=(",", ":")
                )
                self._flatten_messages(input_msgs, "llm.input_messages", result)

            if isinstance(tool_parameters, dict) and "text" in tool_parameters:
                result["input.value"] = tool_parameters["text"]
                result["input.mime_type"] = "text/plain"
            else:
                result["input.value"] = json.dumps(
                    tool_parameters, separators=(",", ":")
                )
                result["input.mime_type"] = "application/json"

        if tool_output:
            result["output.value"] = tool_output
            result["output.mime_type"] = "text/plain"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _flatten_messages(
        self, messages: list[dict], key_prefix: str, result: dict[str, Any]
    ):
        for idx, msg in enumerate(messages):
            for key, value in msg.items():
                clean_key = key.removeprefix("message.")
                dotted = f"{key_prefix}.{idx}.message.{clean_key}"
                if clean_key == "tool_calls" and isinstance(value, list):
                    for ti, tc in enumerate(value):
                        if isinstance(tc, dict):
                            for tk, tv in tc.items():
                                result[
                                    f"{key_prefix}.{idx}.message.tool_calls.{ti}.{tk}"
                                ] = self._serialize_value(tv)
                else:
                    result[dotted] = self._serialize_value(value)

    def _create_input_output_values(
        self,
        attrs: dict[str, Any],
        result: dict[str, Any],
        input_messages: list[dict],
        output_messages: list[dict],
    ):
        span_kind = result.get("openinference.span.kind")
        model_name = (
            result.get("llm.model_name")
            or attrs.get("gen_ai.request.model")
            or "unknown"
        )

        if span_kind not in ("LLM", "AGENT", "CHAIN"):
            return

        if input_messages:
            if (
                len(input_messages) == 1
                and input_messages[0].get("message.role") == "user"
            ):
                result["input.value"] = input_messages[0].get("message.content", "")
                result["input.mime_type"] = "text/plain"
            else:
                result["input.value"] = json.dumps(
                    {"messages": input_messages, "model": model_name},
                    separators=(",", ":"),
                )
                result["input.mime_type"] = "application/json"

        if output_messages:
            last = output_messages[-1]
            content = last.get("message.content", "")
            if span_kind == "LLM":
                result["output.value"] = json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": last.get(
                                    "message.finish_reason", "stop"
                                ),
                                "index": 0,
                                "message": {
                                    "content": content,
                                    "role": last.get("message.role", "assistant"),
                                },
                            }
                        ],
                        "model": model_name,
                        "usage": {
                            "completion_tokens": result.get(
                                "llm.token_count.completion"
                            ),
                            "prompt_tokens": result.get("llm.token_count.prompt"),
                            "total_tokens": result.get("llm.token_count.total"),
                        },
                    },
                    separators=(",", ":"),
                )
                result["output.mime_type"] = "application/json"
            else:
                result["output.value"] = content
                result["output.mime_type"] = "text/plain"

    def _handle_tags(self, attrs: dict[str, Any], result: dict[str, Any]):
        tags = attrs.get("arize.tags") or attrs.get("tag.tags")
        if tags:
            result["tag.tags"] = [tags] if isinstance(tags, str) else tags

    def _map_tools(self, tools_data: Any, result: dict[str, Any]):
        if isinstance(tools_data, str):
            try:
                tools_data = json.loads(tools_data)
            except json.JSONDecodeError:
                return
        if not isinstance(tools_data, list):
            return
        for idx, tool in enumerate(tools_data):
            if isinstance(tool, str):
                result[f"llm.tools.{idx}.tool.name"] = tool
                result[f"llm.tools.{idx}.tool.description"] = f"Tool: {tool}"
            elif isinstance(tool, dict):
                result[f"llm.tools.{idx}.tool.name"] = tool.get("name", "")
                result[f"llm.tools.{idx}.tool.description"] = tool.get(
                    "description", ""
                )
                schema = tool.get("parameters") or tool.get("input_schema")
                if schema:
                    result[f"llm.tools.{idx}.tool.json_schema"] = json.dumps(schema)

    def _map_token_usage(self, attrs: dict[str, Any], result: dict[str, Any]):
        for src, dst in (
            ("gen_ai.usage.prompt_tokens", "llm.token_count.prompt"),
            ("gen_ai.usage.input_tokens", "llm.token_count.prompt"),
            ("gen_ai.usage.completion_tokens", "llm.token_count.completion"),
            ("gen_ai.usage.output_tokens", "llm.token_count.completion"),
            ("gen_ai.usage.total_tokens", "llm.token_count.total"),
        ):
            if value := attrs.get(src):
                result[dst] = value

    def _map_invocation_parameters(self, attrs: dict[str, Any], result: dict[str, Any]):
        params = {}
        for key in ("max_tokens", "temperature", "top_p"):
            if key in attrs:
                params[key] = attrs[key]
        if params:
            result["llm.invocation_parameters"] = json.dumps(
                params, separators=(",", ":")
            )

    def _normalize_message(self, msg: Any) -> dict[str, Any]:
        if not isinstance(msg, dict):
            return {"message.role": "user", "message.content": str(msg)}
        result: dict[str, Any] = {}
        if "role" in msg:
            result["message.role"] = msg["role"]
        if "content" in msg:
            content = msg["content"]
            if isinstance(content, list):
                parts = [
                    str(item["text"])
                    for item in content
                    if isinstance(item, dict) and "text" in item
                ]
                result["message.content"] = " ".join(parts) if parts else ""
            else:
                result["message.content"] = str(content)
        return result

    def _add_metadata(self, attrs: dict[str, Any], result: dict[str, Any]):
        skip = {
            "gen_ai.prompt",
            "gen_ai.completion",
            "gen_ai.agent.tools",
            "agent.tools",
        }
        metadata = {
            k: self._serialize_value(v)
            for k, v in attrs.items()
            if k not in skip and k not in result
        }
        if metadata:
            result["metadata"] = json.dumps(metadata, separators=(",", ":"))

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        try:
            return json.dumps(value, separators=(",", ":"))
        except (TypeError, OverflowError):
            return str(value)

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=None):
        return True
