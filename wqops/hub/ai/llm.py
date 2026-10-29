"""Model access (ADR-0008 item 1, ADR-0023 step 23d): Anthropic Messages API or DeepSeek, called with httpx (no SDK).

Every caller speaks the Anthropic shape (system, messages with tool_use / tool_result blocks, tools with input_schema);
the DeepSeek provider converts to its OpenAI-style chat API and back, so the callers do not change.

    WQO_DEPLOYMENT            us (default) or cn. In China only DeepSeek is used (a filed model); asking for another
                              provider there is a configuration error, and nothing is sent to Anthropic.
    WQO_AI_PROVIDER           claude or deepseek (default: claude in the US, deepseek in China)
    WQO_ANTHROPIC_API_KEY     (or ANTHROPIC_API_KEY) the company's own key for Claude
    WQO_DEEPSEEK_API_KEY      (or DEEPSEEK_API_KEY) the company's own key for DeepSeek
    WQO_AI_MODEL              model id (defaults below)
    WQO_AI_TIMEOUT            seconds per call (default 90)

Without a key the rule engine answers. The model answers in the reader's language (wqops.i18n): a line is added to the
system prompt; quotations, record numbers and the tools' codes stay as they are.
"""

from __future__ import annotations

import json
import os

import httpx

from wqops import i18n as I18N
from wqops.i18n import say

DEFAULT_MODEL = "claude-sonnet-5-5"
API = "https://api.anthropic.com/v1/messages"
VERSION = "2023-06-01"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_API = "https://api.deepseek.com/chat/completions"
PROVIDERS = ("claude", "deepseek")
LANGUAGE_RULE = {
    "en": "Write every answer, summary and text meant for people in English. Keep record numbers, item codes, names, "
          "the codes and choices the tools define, and quotations from documents exactly as they are in the source, "
          "in their original language.",
    "zh": "Write every answer, summary and text meant for people in Simplified Chinese (简体中文). Keep record "
          "numbers, item codes, names, the codes and choices the tools define, and quotations from documents exactly "
          "as they are in the source, in their original language.",
}


class LlmError(RuntimeError):
    pass


def with_language(system: str) -> str:
    """The system prompt with the reader's language added."""
    rule = LANGUAGE_RULE.get(I18N.current())
    return f"{system}\n\n{rule}" if rule else system


def from_env(env=None):
    """The provider this deployment uses (see the module notes)."""
    env = os.environ if env is None else env
    cn = (env.get("WQO_DEPLOYMENT") or "us").strip().lower() == "cn"
    asked = (env.get("WQO_AI_PROVIDER") or "").strip().lower()
    if asked and asked not in PROVIDERS:
        raise ValueError(f"WQO_AI_PROVIDER must be one of {', '.join(PROVIDERS)}, not {asked!r}")
    if cn and asked not in ("", "deepseek"):
        raise ValueError("a deployment in China (WQO_DEPLOYMENT=cn) uses only DeepSeek; remove WQO_AI_PROVIDER "
                         "or set it to deepseek")
    return DeepSeek(env=env) if cn or asked == "deepseek" else Anthropic(env=env)


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
        body = {"model": self.model, "max_tokens": max_tokens, "system": with_language(system), "messages": messages,
                "tools": tools}
        if tool_choice:
            body["tool_choice"] = tool_choice
        try:
            r = self.http.post(
                API,
                headers={"x-api-key": self.key, "anthropic-version": VERSION, "content-type": "application/json"},
                json=body,
            )
        except httpx.HTTPError as exc:
            raise LlmError(say("could not reach the model: {name}", name=type(exc).__name__)) from exc
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise LlmError(say("model error {status_code}: {msg}", status_code=r.status_code, msg=str(msg)[:300]))
        return r.json()


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def to_openai(system: str, messages: list[dict], tools: list[dict], tool_choice: dict | None) -> dict:
    """Anthropic-shaped request -> OpenAI-style chat request (DeepSeek)."""
    out = [{"role": "system", "content": system}]
    for m in messages:
        c = m.get("content")
        if m.get("role") == "assistant":
            blocks = [{"type": "text", "text": c}] if isinstance(c, str) else (c or [])
            msg = {"role": "assistant", "content": _text(blocks) or None}
            calls = [{"id": b["id"], "type": "function",
                      "function": {"name": b["name"],
                                   "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)}}
                     for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
            continue
        if isinstance(c, str):
            out.append({"role": "user", "content": c})
            continue
        for b in c or []:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                rc = b.get("content")
                text = rc if isinstance(rc, str) else _text(rc) if isinstance(rc, list) else json.dumps(rc)
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": text})
        rest = _text(c)
        if rest:
            out.append({"role": "user", "content": rest})
    body = {"messages": out}
    if tools:
        body["tools"] = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                                           "parameters": t.get("input_schema") or {"type": "object"}}}
                         for t in tools]
        kind = (tool_choice or {}).get("type")
        if kind == "tool":
            body["tool_choice"] = {"type": "function", "function": {"name": tool_choice["name"]}}
        elif kind == "any":
            body["tool_choice"] = "required"
    return body


STOP = {"tool_calls": "tool_use", "stop": "end_turn", "length": "max_tokens"}


def from_openai(r: dict) -> dict:
    """OpenAI-style chat response -> Anthropic-shaped response (content blocks, stop_reason, usage)."""
    choice = (r.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = [{"type": "text", "text": msg["content"]}] if msg.get("content") else []
    for call in msg.get("tool_calls") or []:
        fn = call.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError:
            args = {}
        content.append({"type": "tool_use", "id": call.get("id", ""), "name": fn.get("name", ""),
                        "input": args if isinstance(args, dict) else {}})
    u = r.get("usage") or {}
    return {"content": content, "stop_reason": STOP.get(choice.get("finish_reason"), choice.get("finish_reason")),
            "usage": {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)},
            "model": r.get("model")}


class DeepSeek:
    """DeepSeek (OpenAI-style chat completions with function calling), behind the same create() as Anthropic."""

    name = "deepseek"

    def __init__(self, key: str | None = None, model: str | None = None, *, env=None,
                 transport: httpx.BaseTransport | None = None):
        env = os.environ if env is None else env
        self.key = key if key is not None else (env.get("WQO_DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY", ""))
        self.model = model or env.get("WQO_AI_MODEL") or DEEPSEEK_MODEL
        self.http = httpx.Client(timeout=float(env.get("WQO_AI_TIMEOUT", "90")), transport=transport)

    def configured(self) -> bool:
        return bool(self.key)

    def create(self, system: str, messages: list[dict], tools: list[dict], max_tokens: int = 2000,
               tool_choice: dict | None = None) -> dict:
        body = {"model": self.model, "max_tokens": max_tokens,
                **to_openai(with_language(system), messages, tools, tool_choice)}
        try:
            r = self.http.post(DEEPSEEK_API, headers={"authorization": f"Bearer {self.key}",
                                                      "content-type": "application/json"}, json=body)
        except httpx.HTTPError as exc:
            raise LlmError(say("could not reach the model: {name}", name=type(exc).__name__)) from exc
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            raise LlmError(say("model error {status_code}: {msg}", status_code=r.status_code, msg=str(msg)[:300]))
        return from_openai(r.json())
