"""Thin client for a local Ollama server (https://ollama.com).

Ollama is the simplest way to run open-weight models locally: it downloads
models, serves an HTTP API on localhost:11434, and supports tool calling for
many models. This module wraps the few endpoints we need: health, list,
pull (with streamed progress), and chat.
"""

from __future__ import annotations

import json
from typing import Callable, Iterator

import requests

DEFAULT_HOST = "http://localhost:11434"

# Curated tool-calling-capable models worth suggesting in the UI, smallest
# first. Sizes are approximate download footprints.
SUGGESTED_MODELS = [
    {"name": "qwen2.5:7b", "size": "~4.7 GB", "note": "Strong tool use, good default"},
    {"name": "llama3.1:8b", "size": "~4.9 GB", "note": "Reliable general-purpose"},
    {"name": "mistral-nemo:12b", "size": "~7.1 GB", "note": "Solid reasoning"},
    {"name": "qwen2.5:14b", "size": "~9 GB", "note": "Higher quality, needs more RAM"},
    {"name": "qwen2.5:32b", "size": "~20 GB", "note": "Best local quality, heavy"},
    {"name": "llama3.2:3b", "size": "~2 GB", "note": "Lightweight, modest hardware"},
]


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str = DEFAULT_HOST, timeout: float = 600.0):
        self.host = host.rstrip("/")
        self.timeout = timeout

    def is_available(self) -> bool:
        try:
            requests.get(f"{self.host}/api/tags", timeout=3)
            return True
        except requests.RequestException:
            return False

    def list_models(self) -> list[dict]:
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Cannot reach Ollama at {self.host}: {exc}")
        out = []
        for m in resp.json().get("models", []):
            size = m.get("size", 0)
            out.append(
                {
                    "name": m.get("name", "?"),
                    "size_gb": round(size / 1e9, 2) if size else None,
                    "modified": m.get("modified_at", "")[:10],
                }
            )
        return sorted(out, key=lambda m: m["name"])

    def has_model(self, name: str) -> bool:
        base = name.split(":")[0]
        return any(
            m["name"] == name or m["name"].split(":")[0] == base
            for m in self.list_models()
        )

    def pull(self, name: str) -> Iterator[dict]:
        """Stream pull progress. Yields {'status', 'percent'} dicts."""
        try:
            resp = requests.post(
                f"{self.host}/api/pull",
                json={"model": name, "stream": True},
                stream=True,
                timeout=self.timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Pull failed for {name!r}: {exc}")

        for line in resp.iter_lines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in event:
                raise OllamaError(event["error"])
            percent = None
            total, completed = event.get("total"), event.get("completed")
            if total and completed:
                percent = round(completed / total * 100, 1)
            yield {"status": event.get("status", ""), "percent": percent}

    def pull_blocking(self, name: str, on_progress: Callable[[dict], None] | None = None):
        for event in self.pull(name):
            if on_progress:
                on_progress(event)

    def chat(
        self, model: str, messages: list[dict], tools: list[dict] | None = None
    ) -> dict:
        """One non-streaming chat completion. Returns the assistant message
        dict: {role, content, tool_calls?}."""
        payload = {"model": model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=payload, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Chat failed: {exc}")
        data = resp.json()
        if "error" in data:
            raise OllamaError(data["error"])
        return data.get("message", {"role": "assistant", "content": ""})

    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict] | None,
        on_token: Callable[[str], None],
    ) -> dict:
        """Streaming chat. Calls on_token for each text token as it arrives.
        Returns the full assistant message dict (with tool_calls if any)."""
        payload = {"model": model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=payload, stream=True, timeout=self.timeout
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(f"Chat failed: {exc}")

        full_content = ""
        tool_calls: list[dict] = []

        for line in resp.iter_lines():
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in event:
                raise OllamaError(event["error"])
            msg = event.get("message", {})
            chunk = msg.get("content", "") or ""
            if chunk:
                full_content += chunk
                on_token(chunk)
            if msg.get("tool_calls"):
                tool_calls = msg["tool_calls"]

        result: dict = {"role": "assistant", "content": full_content}
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result
