from __future__ import annotations

from types import SimpleNamespace
import asyncio

from gateway.proxy import (
    SseModelRewriter,
    is_fast_route,
    normalize_base,
    prepare_body_for_upstream,
    rewrite_model_field,
)
from gateway.router import adaptive_candidate_score, adaptive_route_for_request, resolve_candidates


def test_remount_vision_with_ardot_tools_to_agent():
    from gateway.proxy import remount_route_for_tools

    body = {
        "model": "识图",
        "tools": [{"type": "function", "function": {"name": "mcp__ardot__batch_edit"}}],
    }
    assert remount_route_for_tools("识图", body) == "Agent"
    assert remount_route_for_tools("vision", body) == "Agent"
    assert remount_route_for_tools("日常", {"tools": [{"function": {"name": "shell"}}]}) == "日常"
    assert remount_route_for_tools("识图", {"messages": []}) == "识图"


def test_adaptive_daily_route_detects_user_intent():
    routers = {
        "日常": {"candidates": ["m1"]},
        "代码": {"candidates": ["coder"]},
        "翻译": {"candidates": ["translator"]},
        "推理": {"candidates": ["reasoner"]},
        "长文": {"candidates": ["long"]},
    }
    assert adaptive_route_for_request(
        "日常",
        {"messages": [{"role": "user", "content": "请调试这段 Python traceback 并修复代码"}]},
        routers,
    ) == "代码"
    assert adaptive_route_for_request(
        "daily",
        {"messages": [{"role": "user", "content": "请严谨分析并逐步推理这个方案"}]},
        routers,
    ) == "推理"
    assert adaptive_route_for_request("快速", {"messages": []}, routers) == "快速"


def test_adaptive_route_uses_current_user_turn_not_assistant_history():
    routers = {
        "日常": {"candidates": ["m1"]},
        "代码": {"candidates": ["coder"]},
    }
    body = {
        "messages": [
            {"role": "assistant", "content": "```python\nraise RuntimeError('traceback')\n```"},
            {"role": "user", "content": "谢谢"},
        ]
    }
    assert adaptive_route_for_request("日常", body, routers) == "日常"


def test_tool_only_payload_is_usable():
    from gateway.app import _usable_chat_payload

    raw = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [{"id": "call-1", "type": "function"}],
                }
            }
        ]
    }
    assert _usable_chat_payload(raw)


def test_adaptive_fast_score_learns_low_ttft_without_ignoring_cold_start_order():
    cold = SimpleNamespace(successes=0, failures=0, last_latency_ms=None)
    assert adaptive_candidate_score("快速", "m1", cold, 0) > adaptive_candidate_score("快速", "m2", cold, 1)

    slow = SimpleNamespace(successes=9, failures=1, last_latency_ms=9000)
    fast = SimpleNamespace(successes=9, failures=1, last_latency_ms=500)
    assert adaptive_candidate_score("快速", "m2", fast, 1) > adaptive_candidate_score("快速", "m1", slow, 0)


def test_rewrite_model_field():
    raw = {"id": "x", "model": "upstream-model", "choices": []}
    out = rewrite_model_field(raw, "daily")
    assert out["model"] == "daily"
    assert raw["model"] == "upstream-model"


def test_normalize_base_adds_v1():
    assert normalize_base("https://api.example.com").endswith("/v1")
    assert normalize_base("https://api.example.com/v1") == "https://api.example.com/v1"


def test_sse_looks_complete():
    rw = SseModelRewriter("小说")
    rw.feed(
        b'data: {"choices":[{"delta":{"content":"hello world"},"finish_reason":null}]}\n\n'
    )
    assert rw.saw_usable
    assert not rw.looks_complete()
    rw.feed(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n')
    rw.feed(b"data: [DONE]\n\n")
    assert rw.looks_complete()

    soft = SseModelRewriter("小说")
    import json as _json

    msg = "让我继续读取第55章："
    soft.feed(
        ("data: " + _json.dumps({"choices": [{"delta": {"content": msg}, "finish_reason": "stop"}]}) + "\n\n").encode(
            "utf-8"
        )
    )
    soft.feed(b"data: [DONE]\n\n")
    assert soft.looks_complete(expect_tools=False)
    assert not soft.looks_complete(expect_tools=True)
    rw = SseModelRewriter("daily")
    part1 = b'data: {"model":"up","cho'
    part2 = b'ices":[]}\n\n'
    out = rw.feed(part1) + rw.feed(part2) + rw.flush()
    assert b'"model": "daily"' in out or b'"model":"daily"' in out


def test_sse_utf8_split_mid_chinese_does_not_corrupt():
    """Regression: TCP may split a UTF-8 char; old rewriter leaked bytes as mojibake."""
    import json as _json

    payload = {
        "model": "upstream-vl",
        "choices": [{"delta": {"content": "一只橘猫蹲在窗台"}, "finish_reason": None}],
    }
    full = ("data: " + _json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")
    # Force a split inside a multi-byte Chinese character.
    cut = None
    for i in range(1, len(full) - 1):
        try:
            full[:i].decode("utf-8")
        except UnicodeDecodeError:
            cut = i
            break
    assert cut is not None, "expected a mid-character split point"
    rw = SseModelRewriter("识图")
    out = rw.feed(full[:cut]) + rw.feed(full[cut:]) + rw.flush()
    text = out.decode("utf-8")
    assert "data: " in text
    assert "橘猫" in text or "\\u6a58\\u732b" in text or "\\u6a58" in text
    # Must not glue a raw second event into content.
    assert text.count("data: ") == 1
    assert '"model": "\\u8bc6\\u56fe"' in text or '"model":"\\u8bc6\\u56fe"' in text or '"model": "识图"' in text or '"model":"识图"' in text


def test_stream_health_updates_only_after_clean_eof(monkeypatch):
    from gateway import proxy as proxy_mod
    from gateway.state import RuntimeState

    event = b'data: {"choices":[{"delta":{"tool_calls":[{"id":"call-1"}]},"finish_reason":"tool_calls"}]}\n\n'

    class Response:
        status_code = 200

        async def aiter_bytes(self):
            yield event
            yield b"data: [DONE]\n\n"

        async def aclose(self):
            return None

    class Client:
        def build_request(self, *args, **kwargs):
            return object()

        async def send(self, *args, **kwargs):
            return Response()

    state = RuntimeState()
    monkeypatch.setattr(proxy_mod, "STATE", state)
    monkeypatch.setattr(proxy_mod, "get_http_client", lambda timeout: Client())
    monkeypatch.setattr(proxy_mod, "_append_usage", lambda row: None)

    async def run():
        _resp, stream_iter, _meta = await proxy_mod.forward_chat(
            provider={"name": "A", "base_url": "https://example.test/v1", "api_key": "sk-x"},
            upstream_model="tool-model",
            client_model="Agent",
            body={"messages": [{"role": "user", "content": "use tool"}], "tools": [{"type": "function"}]},
            timeout_sec=5,
            stream=True,
            stall_sec=1,
        )
        assert stream_iter is not None
        assert state.get("A", "tool-model").successes == 0
        _ = [chunk async for chunk in stream_iter]

    asyncio.run(run())
    health = state.get("A", "tool-model")
    assert health.successes == 1
    assert health.last_ttft_ms is not None


def test_stream_mid_stall_marks_channel_failed(monkeypatch):
    from gateway import proxy as proxy_mod
    from gateway.state import RuntimeState

    event = b'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}]}\n\n'

    class Response:
        status_code = 200

        async def aiter_bytes(self):
            yield event
            await asyncio.sleep(5)

        async def aclose(self):
            return None

    class Client:
        def build_request(self, *args, **kwargs):
            return object()

        async def send(self, *args, **kwargs):
            return Response()

    state = RuntimeState()
    usage_rows = []
    monkeypatch.setattr(proxy_mod, "STATE", state)
    monkeypatch.setattr(proxy_mod, "get_http_client", lambda timeout: Client())
    monkeypatch.setattr(proxy_mod, "_append_usage", usage_rows.append)

    async def run():
        _resp, stream_iter, _meta = await proxy_mod.forward_chat(
            provider={"name": "A", "base_url": "https://example.test/v1", "api_key": "sk-x"},
            upstream_model="unstable",
            client_model="日常",
            body={"messages": [{"role": "user", "content": "hello"}]},
            timeout_sec=5,
            stream=True,
            stall_sec=0.05,
        )
        assert stream_iter is not None
        _ = [chunk async for chunk in stream_iter]

    asyncio.run(run())
    health = state.get("A", "unstable")
    assert health.successes == 0
    assert health.failures == 1
    assert usage_rows[-1]["ok"] is False
    assert "stall" in usage_rows[-1]["error"]


def test_resolve_candidates_prefers_ready_provider():
    providers = [
        {
            "name": "A",
            "api_key": "sk-a",
            "enabled": True,
            "weight": 1,
            "models": ["m1"],
        },
        {
            "name": "B",
            "api_key": "REPLACE_X",
            "enabled": True,
            "weight": 99,
            "models": ["m1"],
        },
    ]
    routers = {"daily": {"candidates": ["m1"]}}
    ordered = resolve_candidates("DAILY", providers, routers)
    assert ordered
    assert all(p["name"] == "A" for p, _ in ordered)


def test_ascii_header_quotes_chinese():
    from gateway.app import _ascii_header

    assert _ascii_header("NVIDIA") == "NVIDIA"
    assert _ascii_header("魔搭").isascii()
    assert "%" in _ascii_header("魔搭")


def test_fast_route_low_reasoning():
    assert is_fast_route("快速")
    assert is_fast_route("fast")
    assert not is_fast_route("日常")
    body = prepare_body_for_upstream(
        {
            "model": "快速",
            "reasoning_effort": "high",
            "max_tokens": 100000,
            "messages": [{"role": "user", "content": "hi"}],
        },
        "快速",
    )
    assert body["reasoning_effort"] == "low"
    assert body["max_tokens"] == 6144


def test_256k_uses_long_context_timing_and_token_cap():
    from gateway.proxy import _route_max_tokens, is_novel_route

    assert not is_fast_route("256k")
    assert is_novel_route("256k")
    assert _route_max_tokens("256k") == 32768


def test_novel_and_code_routes():
    from gateway.proxy import _route_max_tokens, is_coding_route, is_novel_route

    assert is_novel_route("小说")
    assert is_coding_route("代码")
    assert is_coding_route("code")
    assert not is_fast_route("代码")
    assert _route_max_tokens("小说") == 32768
    assert _route_max_tokens("代码") == 16384
    from gateway.proxy import _route_max_tokens, is_complex_route

    assert is_complex_route("复杂")
    assert is_complex_route("complex")
    assert not is_complex_route("日常")
    assert _route_max_tokens("复杂") == 32768
    body = prepare_body_for_upstream(
        {"model": "复杂", "max_tokens": 999999, "messages": [{"role": "user", "content": "hi"}]},
        "复杂",
    )
    assert body["max_tokens"] == 32768


def test_trim_old_tool_messages():
    big = "x" * 20000
    body = prepare_body_for_upstream(
        {
            "model": "日常",
            "messages": [
                {"role": "user", "content": "q1"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
                {"role": "tool", "tool_call_id": "1", "content": big},
                {"role": "user", "content": "q2"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "2"}]},
                {"role": "tool", "tool_call_id": "2", "content": big},
                {"role": "user", "content": "q3"},
                {"role": "assistant", "content": None, "tool_calls": [{"id": "3"}]},
                {"role": "tool", "tool_call_id": "3", "content": big},
            ],
        },
        "日常",
    )
    msgs = body["messages"]
    # oldest tool truncated; last two kept full
    assert "truncated" in msgs[2]["content"]
    assert len(msgs[5]["content"]) == 20000
    assert len(msgs[8]["content"]) == 20000
    assert body["max_tokens"] == 12288
