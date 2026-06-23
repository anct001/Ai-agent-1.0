"""The agentic core: an LLM + shared tools + risk-gated execution.

`InvestmentAgent` is a thin façade that picks an engine based on settings:
  * AnthropicEngine — Claude via the Anthropic API (adaptive thinking,
    server-side web search). The default.
  * OllamaEngine    — a local open-weight model served by Ollama. No
    web search (that tool is Anthropic-side), but every other tool works.

Both engines use the same `Toolkit`, so capabilities and the risk gate are
identical regardless of which model is driving.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .config import Settings
from .memory import Journal
from .portfolio import Portfolio
from .prompts import SYSTEM_PROMPT
from .risk import RiskManager
from .toolkit import Toolkit, anthropic_tools, openai_tools

MAX_ITERATIONS = 40


class _BaseEngine:
    """Shared conversation persistence; subclasses implement the model loop."""

    MAX_HISTORY_MESSAGES = 60

    def __init__(self, toolkit: Toolkit, history_path: Path | None):
        self.toolkit = toolkit
        self.history_path = history_path
        self.messages: list[dict] = self._load_history()

    def _load_history(self) -> list[dict]:
        if self.history_path and self.history_path.exists():
            try:
                return json.loads(self.history_path.read_text())
            except json.JSONDecodeError:
                return []
        return []

    def _save_history(self) -> None:
        self._trim_history()
        if self.history_path:
            self.history_path.write_text(json.dumps(self.messages, default=str))

    def _trim_history(self) -> None:
        """Bound context; cut only at a plain user-text message so tool
        request/result pairs are never orphaned."""
        if len(self.messages) <= self.MAX_HISTORY_MESSAGES:
            return
        start = len(self.messages) - self.MAX_HISTORY_MESSAGES
        for i in range(start, len(self.messages)):
            msg = self.messages[i]
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                self.messages = self.messages[i:]
                return

    def reset(self) -> None:
        self.messages = []
        if self.history_path and self.history_path.exists():
            self.history_path.unlink()


class AnthropicEngine(_BaseEngine):
    name = "anthropic"

    def __init__(self, settings: Settings, toolkit: Toolkit, history_path=None):
        super().__init__(toolkit, history_path)
        import anthropic

        self.settings = settings
        self.model = settings.model
        self.client = anthropic.Anthropic()
        self.tools = anthropic_tools(include_web_search=True)

    @staticmethod
    def _serializable(messages: list[dict]) -> list[dict]:
        out = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, list):
                content = [
                    b.model_dump(exclude_none=True) if hasattr(b, "model_dump") else b
                    for b in content
                ]
            out.append({"role": msg["role"], "content": content})
        return out

    def _save_history(self) -> None:
        self.messages = self._serializable(self.messages)
        super()._save_history()

    def transcript(self) -> list[dict]:
        out = []
        for msg in self._serializable(self.messages):
            if msg["role"] == "user" and isinstance(msg["content"], str):
                out.append({"role": "user", "text": msg["content"]})
            elif msg["role"] == "assistant" and isinstance(msg["content"], list):
                text = "".join(
                    b.get("text", "")
                    for b in msg["content"]
                    if isinstance(b, dict) and b.get("type") == "text"
                )
                if text.strip():
                    out.append({"role": "agent", "text": text})
        return out

    def run_turn(self, user_message: str, on_text: Callable[[str], None]) -> str:
        self.messages.append({"role": "user", "content": user_message})

        for _ in range(MAX_ITERATIONS):
            with self.client.messages.stream(
                model=self.model,
                max_tokens=self.settings.max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                thinking={"type": "adaptive"},
                output_config={"effort": self.settings.effort},
                tools=self.tools,
                messages=self.messages,
            ) as stream:
                for text in stream.text_stream:
                    on_text(text)
                response = stream.get_final_message()

            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "tool_use":
                results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    on_text(f"\n[tool: {block.name}]\n")
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": self.toolkit.execute_json(block.name, block.input),
                        }
                    )
                self.messages.append({"role": "user", "content": results})
                continue

            if response.stop_reason == "pause_turn":
                continue  # server-side tool paused; re-send to resume

            if response.stop_reason == "refusal":
                on_text("\n[The model declined this request for safety reasons.]\n")
            break

        self._save_history()
        last = self.messages[-1]
        if last["role"] != "assistant" or not isinstance(last["content"], list):
            return ""
        return next(
            (
                b["text"]
                for b in last["content"]
                if isinstance(b, dict) and b.get("type") == "text"
            ),
            "",
        )


class OllamaEngine(_BaseEngine):
    """Local open-weight model via Ollama. OpenAI-style tool calling; no
    streaming (tool calls are most reliable from a complete response)."""

    name = "ollama"

    def __init__(self, settings: Settings, toolkit: Toolkit, history_path=None):
        super().__init__(toolkit, history_path)
        from .llm.ollama import OllamaClient

        self.model = settings.ollama_model
        self.client = OllamaClient(settings.ollama_host)
        self.tools = openai_tools()

    def transcript(self) -> list[dict]:
        out = []
        for msg in self.messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                out.append({"role": "user", "text": msg["content"]})
            elif msg.get("role") == "assistant" and msg.get("content", "").strip():
                out.append({"role": "agent", "text": msg["content"]})
        return out

    @staticmethod
    def _tool_args(call: dict) -> dict:
        args = call.get("function", {}).get("arguments", {})
        if isinstance(args, str):
            try:
                return json.loads(args)
            except json.JSONDecodeError:
                return {}
        return args or {}

    def run_turn(self, user_message: str, on_text: Callable[[str], None]) -> str:
        if not self.client.is_available():
            msg = (
                "Local model server (Ollama) is not reachable at "
                f"{self.client.host}. Start it with `ollama serve` and pull a "
                "model, or switch LLM_PROVIDER back to anthropic."
            )
            on_text(msg)
            return msg

        self.messages.append({"role": "user", "content": user_message})
        request_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        final_text = ""

        for _ in range(MAX_ITERATIONS):
            message = self.client.chat(
                self.model, request_messages + self.messages, self.tools
            )
            self.messages.append(message)
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                final_text = message.get("content", "") or ""
                on_text(final_text)
                break

            # Surface any text the model emitted alongside its tool calls.
            if message.get("content"):
                on_text(message["content"])
            for call in tool_calls:
                name = call.get("function", {}).get("name", "")
                on_text(f"\n[tool: {name}]\n")
                result = self.toolkit.execute_json(name, self._tool_args(call))
                self.messages.append(
                    {"role": "tool", "tool_name": name, "content": result}
                )

        self._save_history()
        return final_text


def _build_engine(settings, toolkit, history_path):
    if settings.llm_provider == "ollama":
        return OllamaEngine(settings, toolkit, history_path)
    return AnthropicEngine(settings, toolkit, history_path)


class InvestmentAgent:
    """Façade over the active LLM engine. Keeps the constructor signature the
    CLI and server already use."""

    def __init__(
        self,
        settings: Settings,
        portfolio: Portfolio,
        broker,
        risk: RiskManager,
        journal: Journal,
        approve_fn: Callable[[dict], bool] | None = None,
        history_path: Path | None = None,
    ):
        from .orders import OrderBook
        from .stops import StopBook

        self.settings = settings
        self.portfolio = portfolio
        stop_book = StopBook(settings.data_dir / "stops.json")
        order_book = OrderBook(settings.data_dir / "pending_orders.json")
        self.toolkit = Toolkit(
            portfolio,
            broker,
            risk,
            journal,
            approve_fn,
            stop_book=stop_book,
            order_book=order_book,
        )
        self.engine = _build_engine(settings, self.toolkit, history_path)

    @property
    def provider(self) -> str:
        return self.engine.name

    @property
    def model(self) -> str:
        return self.engine.model

    def run_turn(self, user_message: str, on_text: Callable[[str], None]) -> str:
        return self.engine.run_turn(user_message, on_text)

    def transcript(self) -> list[dict]:
        return self.engine.transcript()

    def reset(self) -> None:
        self.engine.reset()
