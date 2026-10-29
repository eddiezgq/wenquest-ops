"""AI in the reader's language and the DeepSeek provider (ADR-0023, step 23d).

No real model is called: the providers talk to httpx mock transports that record the requests.
"""

import json

import httpx
import pytest

from tests.test_ai import DANA, ctx, final
from tests.test_ai import world as world  # noqa: PLC0414 - the fixture, used by name
from wqops import i18n as I18N
from wqops.hub.ai import agent as AG
from wqops.hub.ai import llm as L
from wqops.hub.ai import tools as T

ZH = json.loads((I18N.CATALOG_DIR / "zh.json").read_text(encoding="utf-8"))


class Recorder:
    """A mock HTTP server: answers in turn and keeps every request with its host."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append({"host": request.url.host, "path": request.url.path, "headers": dict(request.headers),
                              "body": json.loads(request.content)})
        return httpx.Response(200, json=self.replies.pop(0))

    def transport(self):
        return httpx.MockTransport(self.handle)


def ds_tool_call(name, args, call_id="call_1"):
    call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
    return {"model": "deepseek-chat", "usage": {"prompt_tokens": 120, "completion_tokens": 15},
            "choices": [{"finish_reason": "tool_calls",
                         "message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}


def ds_text(text):
    return {"model": "deepseek-chat", "choices": [{"finish_reason": "stop", "message": {"role": "assistant",
                                                                                       "content": text}}],
            "usage": {"prompt_tokens": 300, "completion_tokens": 40}}


def test_the_provider_follows_the_deployment():
    assert isinstance(L.from_env({}), L.Anthropic)
    assert isinstance(L.from_env({"WQO_AI_PROVIDER": "deepseek"}), L.DeepSeek)
    cn = L.from_env({"WQO_DEPLOYMENT": "cn", "WQO_ANTHROPIC_API_KEY": "a-key", "WQO_DEEPSEEK_API_KEY": "d-key"})
    assert isinstance(cn, L.DeepSeek) and cn.key == "d-key" and cn.model == "deepseek-chat"
    assert not L.from_env({"WQO_DEPLOYMENT": "cn", "WQO_ANTHROPIC_API_KEY": "a-key"}).configured()  # no Claude fallback
    with pytest.raises(ValueError, match="only DeepSeek"):
        L.from_env({"WQO_DEPLOYMENT": "cn", "WQO_AI_PROVIDER": "claude"})
    with pytest.raises(ValueError, match="WQO_AI_PROVIDER"):
        L.from_env({"WQO_AI_PROVIDER": "gpt"})


def test_the_model_is_told_the_readers_language():
    rec = Recorder(final("ok"), final("好的"))
    m = L.Anthropic("k", "m", transport=rec.transport())
    m.create("You help.", [{"role": "user", "content": "hi"}], [])
    with I18N.use("zh"):
        m.create("You help.", [{"role": "user", "content": "你好"}], [])
    en, zh = (r["body"]["system"] for r in rec.requests)
    assert en.startswith("You help.") and "in English" in en
    assert zh.startswith("You help.") and "Simplified Chinese" in zh and "quotations" in zh


def test_deepseek_speaks_the_same_shape_as_the_callers():
    rec = Recorder(ds_tool_call("get_metric", {"name": "shortages"}), ds_text("WIDGET-A 短缺 50。"))
    m = L.DeepSeek("d-key", transport=rec.transport())
    tools = [{"name": "get_metric", "description": "A metric", "input_schema": {"type": "object"}}]
    with I18N.use("zh"):
        r1 = m.create("You help.", [{"role": "user", "content": "缺什么？"}], tools, 500,
                      tool_choice={"type": "tool", "name": "get_metric"})
    assert r1["stop_reason"] == "tool_use" and r1["usage"] == {"input_tokens": 120, "output_tokens": 15}
    assert r1["content"] == [{"type": "tool_use", "id": "call_1", "name": "get_metric", "input": {"name": "shortages"}}]
    req = rec.requests[0]
    assert req["host"] == "api.deepseek.com" and req["path"] == "/chat/completions"
    assert req["headers"]["authorization"] == "Bearer d-key"
    b = req["body"]
    assert b["model"] == "deepseek-chat" and b["max_tokens"] == 500
    assert b["messages"][0]["role"] == "system" and "Simplified Chinese" in b["messages"][0]["content"]
    assert b["messages"][1] == {"role": "user", "content": "缺什么？"}
    assert b["tools"] == [{"type": "function", "function": {"name": "get_metric", "description": "A metric",
                                                            "parameters": {"type": "object"}}}]
    assert b["tool_choice"] == {"type": "function", "function": {"name": "get_metric"}}
    # the second round: the tool call and its result go back as an assistant message and a tool message
    r2 = m.create("You help.", [{"role": "user", "content": "缺什么？"},
                                {"role": "assistant", "content": r1["content"]},
                                {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "call_1",
                                                              "content": '{"short": 50}'}]}], tools)
    assert r2 == {"content": [{"type": "text", "text": "WIDGET-A 短缺 50。"}], "stop_reason": "end_turn",
                  "usage": {"input_tokens": 300, "output_tokens": 40}, "model": "deepseek-chat"}
    msgs = rec.requests[1]["body"]["messages"]
    assert msgs[2] == {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function", "function": {"name": "get_metric", "arguments": '{"name": "shortages"}'}}]}
    assert msgs[3] == {"role": "tool", "tool_call_id": "call_1", "content": '{"short": 50}'}
    assert "tool_choice" not in rec.requests[1]["body"]


def test_a_china_deployment_sends_nothing_to_anthropic(world):
    rec = Recorder(ds_tool_call("get_metric", {"name": "shortages"}),
                   ds_text("WIDGET-A 短缺 50 [Item:WIDGET-A]。建议订购 120 件。"))
    env = {"WQO_DEPLOYMENT": "cn", "WQO_ANTHROPIC_API_KEY": "a-key", "WQO_DEEPSEEK_API_KEY": "d-key"}
    m = L.from_env(env)
    m.http = httpx.Client(transport=rec.transport())
    with I18N.use("zh"):
        out = AG.ask(ctx(world, DANA), "现在缺什么货？", m)
    assert {r["host"] for r in rec.requests} == {"api.deepseek.com"}
    assert out["engine"] == "model" and out["model"] == "deepseek-chat"
    assert out["unverified"] == ["建议订购 120 件。"]              # numbers are checked in Chinese sentences too
    run = world.execute("select * from ai_runs where id = %s", (out["run_id"],)).fetchone()
    assert run["usage"] == {"input_tokens": 420, "output_tokens": 55}


def test_numbers_are_checked_next_to_chinese_characters():
    corpus = '{"item": "ANCHOR-38", "short": 63, "due": "2026-10-26", "value": 4377.9}'
    assert AG.verify("ANCHOR-38 缺63件，应于2026-10-26到货。库存价值 4,377.90。", corpus) == []
    assert AG.verify("缺货 63 件。应订购240件。", corpus) == ["应订购240件。"]
    assert AG.verify("应于2026-10-27到货。", corpus) == ["应于2026-10-27到货。"]


def test_the_rule_engine_answers_in_chinese(world):
    with I18N.use("zh"):
        late = AG.ask(ctx(world, DANA), "哪些订单迟交了？")
        named = AG.ask(ctx(world, DANA), "SO-8 怎么样？")
        hello = AG.ask(ctx(world, DANA), "你好")
    assert late["engine"] == "rules" and late["verified"]
    assert "近 30 天按时交付率：50%。" in late["answer"] and "[SalesOrder:SO-8]" in late["answer"]
    assert [c["tool"] for c in late["tool_calls"]] == ["get_metric", "list_anomalies"]
    assert "原因：" in named["answer"] and named["verified"]
    assert hello["answer"] == ZH[AG.HELP]


def test_the_rule_engines_texts_have_chinese():
    assert AG.HELP in ZH
    assert not [k for k in AG.FIELD_NAMES.values() if k not in ZH]
    assert set(AG.SHOWN[1:]) == set(AG.FIELD_NAMES)


def test_the_ai_status_names_the_provider():
    assert L.DeepSeek("k").name == "deepseek" and L.Anthropic("k").name == "claude"
    assert {t.name for t in T.READ_TOOLS}                          # the same tools for every provider
