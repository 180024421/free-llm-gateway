from __future__ import annotations

from gateway.proxy import (
    SseModelRewriter,
    is_fast_route,
    normalize_base,
    prepare_body_for_upstream,
    rewrite_model_field,
)
from gateway.router import resolve_candidates


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
