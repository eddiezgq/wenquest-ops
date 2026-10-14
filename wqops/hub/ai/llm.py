"""Model access (ADR-0008 item 1): Anthropic Messages API with tool use, called with httpx (no SDK).

    WQO_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)   the company's own key; without it the rule engine answers
    WQO_AI_MODEL                                    model id (default below)
    WQO_AI_TIMEOUT                                  seconds per call (default 90)

Other providers can be added behind the same ``create`` method.
"""

from __future__ import annotations

import os

import httpx

DEFAULT_MODEL = "claude-sonnet-5-5"
API = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"


class LlmError(RuntimeError):
    pass


class Anthropic:
    name = "claude"

    def __init__(
        self,
        key: str | None = None,
        model: str | None = None,
        *,
        env=None,
        transport: httpx.BaseTransport | None = None,
    ):
        env = os.environ if env is None else env
        self.key = key if key is not None else (env.get("WQO_ANTHROPIC_API_KEY") or env.get("ANTHROPIC_API_KEY", ""))
        self.model = model or env.get("WQO_AI_MODEL") or DEFAULT_MODEL
        self.http = httpx.Client(timeout=float(env.get("WQO_AI_TIMEOUT", "90")), transport=transport)

    def configured(self) -> bool:
        return bool(self.key)

    def create(self, system: str, messages: list[dict], tools: list[dict], max_tokens: int = 2000,
               tool_choice: dict | None = None) -> dict:
        """One Messages API call; returns the response (content blocks, stop_reason, usage)."""
        body = {"model": self.model, "max_tokens": max_tokens, "system": system, "messages": messages, "tools": tools}
        if tool_choice:
            body["tool_choice"] = tool_choice
        try:
            r = self.http.post(
                API,
                headers={"x-api-key": self.key, "anthropic-version": VERSION, "content-type": "application/json"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise LlmError(f"could not reach the model: {type(exc).__name__}") from exc
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise LlmError(f"model error {r.status_code}: {str(msg)[:300]}")
        return r.json()
