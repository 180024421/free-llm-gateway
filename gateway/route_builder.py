# -*- coding: utf-8 -*-
"""Build router candidates: top-N per use-case, balancing reliability, speed, accuracy."""
from __future__ import annotations

import json
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import DATA_DIR, load_config, load_providers, save_routers
from .meta import apply_alias, is_non_chat_model

TOP_N = 12
MIN_CALLS_BLACKLIST = 5
MIN_SUCCESS_BLACKLIST = 0.15

USAGE_PATH = DATA_DIR / "usage.jsonl"

# 永久免费小杯 / 聚合 free 池：能力弱、易失败，日常路由放到末尾兜底。
_FREE_FALLBACK = re.compile(
    r":free\b|openrouter/free|\b4b\b|\b7b\b|\b8b\b|lite|mini|instant|nemo(?!tron)|"
    r"sensenova-6\.[67]-flash-lite|allam-2|lfm-|llm7|kilo-auto",
    re.I,
)

# 日额度/赠送额度里更强的模型：日常优先尝试这些，再落到 free 兜底。
_DAILY_QUALITY_PIN = (
    "qwen3.8-max",
    "qwen3.7-plus",
    "deepseek-ai/DeepSeek-V4-Pro",
    "deepseek-v4-pro",
    "Qwen/Qwen3.5-397B-A17B",
    "Qwen/Qwen3-235B-A22B-Instruct-2507",
    "glm-5.2",
    "nvidia/nemotron-3-super-120b-a12b",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "openai/gpt-oss-120b",
    "gpt-oss-120b",
    "qwen3.6-plus",
    "qwen3.5-plus",
    "qwen-plus",
    "qwen3-max",
    "Qwen/Qwen3.5-122B-A10B",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "deepseek-v4-flash",
    "qwen3.5-flash",
    "qwen-flash",
    "doubao-seed-1-6-251015",
    "hunyuan-turbos-latest",
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "meta/llama-3.3-70b-instruct",
    "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "@cf/openai/gpt-oss-120b",
    "gemini-2.5-flash",
    "Qwen/Qwen3.5-27B",
    "glm-4.7",
)

_NOVEL_AVOID = re.compile(
    r"397b|v4-pro|kimi|z-ai|vl|vision|thinking|glm-5|gpt-oss|gemini|openrouter|cerebras|groq",
    re.I,
)
_NOVEL_PIN = (
    "nvidia/nemotron-3-super-120b-a12b",
    "deepseek-v4-flash",
    "sensenova-6.8-flash-lite",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "Qwen/Qwen3.5-122B-A10B",
    "doubao-seed-1-6-251015",
    "hunyuan-turbos-latest",
    "hunyuan-lite",
    "qwen-plus",
    "qwen3.7-plus",
    "qwen3.5-plus",
)

# 识图：强度优先（同档再靠稳定性）。重建时会把「当前可用」整段提到前面。
_VISION_STRENGTH_PIN = (
    "Qwen/Qwen3-VL-235B-A22B-Instruct",
    "Qwen/Qwen3-VL-8B-Instruct",
    "nvidia/nemotron-nano-12b-v2-vl",
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "gemma-4-31b",
    "google/gemma-4-31b-it:free",
    "meta/llama-3.2-11b-vision-instruct",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash",
)

ROUTE_ALIASES: dict[str, set[str]] = {
    "日常": {"日常", "daily", "auto", "1m"},
    "快速": {"快速", "fast", "256k"},
    "复杂": {"复杂", "complex"},
    "小说": {"小说", "novel"},
    "代码": {"代码", "code"},
    "识图": {"识图", "vision"},
    "翻译": {"翻译", "translate"},
    "总结": {"总结", "summarize", "summary"},
    "推理": {"推理", "reasoning", "think"},
    "长文": {"长文", "longctx", "long", "256k", "1m"},
    "Agent": {"agent", "Agent", "工具"},
}

# Heuristic capability tiers (0~1). Used when usage samples are sparse.
_ACCURACY_ULTRA = re.compile(
    r"397b|550b|235b|122b|nemotron-3-super|v4-pro|deepseek-v4-pro|glm-5|thinking|magistral",
    re.I,
)
_ACCURACY_HIGH = re.compile(r"70b|80b|49b|30b|pro|coder|gpt-oss-120b|235b", re.I)
_ACCURACY_MID = re.compile(r"27b|35b|flash(?!-lite)|instruct|glm-4", re.I)
_ACCURACY_LOW = re.compile(r"\b8b\b|\b7b\b|\b4b\b|lite|mini|nano|small|instant|nemo", re.I)
_SPEED_FAST = re.compile(r"flash|lite|\b8b\b|\b7b\b|mini|instant|small|sensenova", re.I)


@dataclass
class Stat:
    ok: int = 0
    fail: int = 0
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.ok + self.fail

    @property
    def rate(self) -> float:
        return self.ok / self.total if self.total else 0.0

    @property
    def median_latency_ms(self) -> float | None:
        if not self.latencies_ms:
            return None
        return float(statistics.median(self.latencies_ms))

    def add(self, success: bool, latency_ms: float | None = None) -> None:
        if success:
            self.ok += 1
            if latency_ms is not None and latency_ms > 0:
                self.latencies_ms.append(float(latency_ms))
        else:
            self.fail += 1


@dataclass
class RouteProfile:
    cn: str
    en: str
    description: str
    matcher: Callable[[str], bool]
    usage_keys: set[str] = field(default_factory=set)
    reliability_w: float = 0.40
    accuracy_w: float = 0.35
    speed_w: float = 0.25
    min_accuracy: float = 0.0


def _compile(*parts: str) -> Callable[[str], bool]:
    rx = re.compile("|".join(parts), re.I)

    def _m(model: str) -> bool:
        return bool(rx.search(model))

    return _m


PROFILES: list[RouteProfile] = [
    RouteProfile(
        "日常",
        "daily",
        "综合日常：日额度/强模型优先，免费小杯兜底（最多12个）",
        lambda m: not is_non_chat_model(m),
        ROUTE_ALIASES["日常"],
        reliability_w=0.40,
        accuracy_w=0.45,
        speed_w=0.15,
        min_accuracy=0.55,
    ),
    RouteProfile(
        "快速",
        "fast",
        "真·快速：优先 Flash/小模型，兼顾可用成功率",
        _compile(r"flash", r"lite", r"\b8b\b", r"\b7b\b", r"mini", r"instant", r"small", r"nemo", r"sensenova"),
        ROUTE_ALIASES["快速"],
        reliability_w=0.35,
        accuracy_w=0.15,
        speed_w=0.50,
        min_accuracy=0.0,
    ),
    RouteProfile(
        "复杂",
        "complex",
        "复杂任务：高准确度大杯优先，成功率过滤",
        _compile(r"397b", r"235b", r"122b", r"nemotron-3-super", r"v4-pro", r"pro", r"70b", r"glm-5", r"gemini", r"gpt-oss-120b", r"qwen-plus", r"qwen3\.8", r"qwen3\.7", r"qwen3\.6"),
        ROUTE_ALIASES["复杂"],
        reliability_w=0.35,
        accuracy_w=0.55,
        speed_w=0.10,
        min_accuracy=0.70,
    ),
    RouteProfile(
        "小说",
        "novel",
        "小说长文：准确度 + 稳定性优先，避免限流大杯",
        _compile(r"122b", r"235b", r"80b", r"nemotron-3-super", r"v4-pro", r"glm-5", r"35b"),
        ROUTE_ALIASES["小说"],
        reliability_w=0.40,
        accuracy_w=0.45,
        speed_w=0.15,
        min_accuracy=0.60,
    ),
    RouteProfile(
        "代码",
        "code",
        "写代码：Coder/工程模型，准确度优先",
        _compile(r"coder", r"code", r"gpt-oss", r"deepseek-v4-pro", r"glm-4\.7"),
        ROUTE_ALIASES["代码"],
        reliability_w=0.35,
        accuracy_w=0.50,
        speed_w=0.15,
        min_accuracy=0.55,
    ),
    RouteProfile(
        "识图",
        "vision",
        "多模态识图：VL 准确度 + 成功率",
        _compile(r"vl", r"vision", r"gemini.*flash", r"gemma", r"phi-3-vision", r"internvl"),
        ROUTE_ALIASES["识图"],
        reliability_w=0.35,
        accuracy_w=0.45,
        speed_w=0.20,
        min_accuracy=0.50,
    ),
    RouteProfile(
        "翻译",
        "translate",
        "翻译：快且准的多语言 Flash",
        _compile(r"flash", r"lite", r"mini", r"8b", r"7b", r"gemini", r"mistral-small", r"qwen3-8b", r"27b"),
        ROUTE_ALIASES["翻译"],
        reliability_w=0.35,
        accuracy_w=0.40,
        speed_w=0.25,
        min_accuracy=0.40,
    ),
    RouteProfile(
        "总结",
        "summarize",
        "总结摘要：准确压缩 + 响应快",
        _compile(r"flash", r"lite", r"instruct", r"8b", r"27b", r"35b", r"sensenova", r"mini"),
        ROUTE_ALIASES["总结"],
        reliability_w=0.35,
        accuracy_w=0.40,
        speed_w=0.25,
        min_accuracy=0.45,
    ),
    RouteProfile(
        "推理",
        "reasoning",
        "深度推理：Thinking/Pro 高准确度",
        _compile(r"thinking", r"reason", r"397b", r"122b", r"pro", r"nemotron", r"glm-5", r"magistral"),
        ROUTE_ALIASES["推理"],
        reliability_w=0.30,
        accuracy_w=0.55,
        speed_w=0.15,
        min_accuracy=0.75,
    ),
    RouteProfile(
        "长文",
        "longctx",
        "超长上下文：窗口大且输出稳定",
        _compile(r"flash-0731", r"v4-flash", r"122b", r"80b", r"kimi", r"256k", r"1m", r"235b"),
        ROUTE_ALIASES["长文"],
        reliability_w=0.40,
        accuracy_w=0.40,
        speed_w=0.20,
        min_accuracy=0.55,
    ),
    RouteProfile(
        "Agent",
        "agent",
        "Agent 工具：优先工具调用强的文本模型（排除 VL）",
        _compile(
            r"minimax",
            r"deepseek-v4",
            r"coder",
            r"gpt-oss",
            r"nemotron-3-super",
            r"nemotron-super",
            r"30b",
            r"glm-4\.7",
            r"sensenova.*flash",
        ),
        ROUTE_ALIASES["Agent"],
        reliability_w=0.40,
        accuracy_w=0.45,
        speed_w=0.15,
        min_accuracy=0.55,
    ),
]


# Agent / 画布工具：强度优先；绝不混入 VL（识图模型不会好好调 Ardot）。
_AGENT_STRENGTH_PIN = (
    "minimaxai/minimax-m3",
    "deepseek-v4-flash",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "nvidia/nemotron-3-super-120b-a12b",
    "Qwen/Qwen3-Coder-30B-A3B-Instruct",
    "openai/gpt-oss-120b",
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "sensenova-6.8-flash-lite",
)

def _is_vision_model(model: str) -> bool:
    return bool(re.search(r"(?:^|/)(?:.*-)?vl(?:-|$)|vision|internvl|phi-3-vision", model or "", re.I))


def _apply_agent_preference(pool: list[str]) -> list[str]:
    """Agent/Ardot：排除 VL；可用工具强模型按 PIN 置顶。"""
    text_only = [m for m in pool if not _is_vision_model(m)]
    if not text_only:
        text_only = list(pool)
    pin_rank = {m.lower(): i for i, m in enumerate(_AGENT_STRENGTH_PIN)}

    def key(m: str) -> tuple[int, str]:
        return (pin_rank.get(m.lower(), 10_000), m.lower())

    ordered: list[str] = []
    seen: set[str] = set()
    for pref in _AGENT_STRENGTH_PIN:
        hit = next((m for m in text_only if m.lower() == pref.lower() and m not in seen), None)
        if hit:
            ordered.append(hit)
            seen.add(hit)
    for m in sorted(text_only, key=key):
        if m not in seen:
            ordered.append(m)
            seen.add(m)
    return ordered


def model_accuracy_tier(model: str) -> float:
    m = model or ""
    # Dedicated VL / multimodal: prefer real vision models over tiny text LLMs.
    if re.search(r"qwen3-vl-235b|internvl|gpt-4o(?!-mini)", m, re.I):
        return 0.96
    if re.search(r"qwen3-vl|nemotron-.*-vl|llama-3\.2-.*vision|phi-3-vision|gemini-.*flash|qwen-vl", m, re.I):
        return 0.88
    if _FREE_FALLBACK.search(m) and not re.search(r"120b|70b|nemotron-3-super|glm-5\.2:free", m, re.I):
        return 0.32
    if _ACCURACY_ULTRA.search(m):
        return 0.95
    if re.search(r"gemini-flash|gemini-3|qwen3\.8-max|qwen3\.7-plus|qwen3\.6-plus|qwen3\.5-plus|qwen-plus|qwen3-max|gpt-oss-120b|deepseek-v4-pro", m, re.I):
        return 0.86
    if _ACCURACY_HIGH.search(m):
        return 0.82
    if _ACCURACY_MID.search(m):
        return 0.62
    if _ACCURACY_LOW.search(m):
        return 0.35
    return 0.55


def _is_free_fallback_model(model: str) -> bool:
    m = model or ""
    if re.search(r"nemotron-3-super.*:free|glm-5\.2:free|gpt-oss-120b", m, re.I):
        return False
    return bool(_FREE_FALLBACK.search(m))


def _apply_quality_then_free(pool: list[str]) -> list[str]:
    """日额度/强模型置顶，免费小杯与 :free 池放到末尾兜底。"""
    if not pool:
        return []
    pin_rank = {m.lower(): i for i, m in enumerate(_DAILY_QUALITY_PIN)}
    quality: list[str] = []
    free: list[str] = []
    seen: set[str] = set()

    for pref in _DAILY_QUALITY_PIN:
        hit = next((m for m in pool if m.lower() == pref.lower() and m not in seen), None)
        if hit:
            quality.append(hit)
            seen.add(hit)

    for m in pool:
        if m in seen:
            continue
        if _is_free_fallback_model(m):
            free.append(m)
        else:
            quality.append(m)
        seen.add(m)

    def qkey(m: str) -> tuple[int, float, str]:
        return (pin_rank.get(m.lower(), 10_000), -model_accuracy_tier(m), m.lower())

    quality.sort(key=qkey)
    free.sort(key=lambda m: (-model_accuracy_tier(m), m.lower()))
    return quality + free


def _vision_model_usable(model: str, providers: list[dict[str, Any]]) -> bool:
    """True if at least one enabled provider path is not in circuit cooldown."""
    from .state import STATE

    now = time.time()
    saw = False
    for p in providers:
        if not p.get("enabled", True):
            continue
        key = (p.get("api_key") or "").strip()
        if not key or key.startswith("REPLACE_"):
            continue
        models = [str(x) for x in (p.get("models") or [])]
        disabled = {str(x) for x in (p.get("disabled_models") or [])}
        canon = next((m for m in models if m.lower() == model.lower() and m not in disabled), None)
        if not canon:
            continue
        saw = True
        h = STATE.get(p.get("name") or "?", canon)
        if now < float(getattr(h, "open_until", 0.0) or 0.0):
            continue
        total = int(h.successes) + int(h.failures)
        if total >= 8 and int(h.successes) / total < 0.15:
            continue
        if int(h.consecutive_failures) >= 8 and int(h.successes) == 0:
            continue
        return True
    return False if saw else True


def _apply_vision_preference(pool: list[str], providers: list[dict[str, Any]]) -> list[str]:
    """可用的在前；同档按强度 PIN；不可用的强模型留作恢复后的后备。"""
    if not pool:
        return []
    pin_rank = {m.lower(): i for i, m in enumerate(_VISION_STRENGTH_PIN)}

    def strength_key(m: str) -> tuple[int, str]:
        return (pin_rank.get(m.lower(), 10_000), m.lower())

    healthy = [m for m in pool if _vision_model_usable(m, providers)]
    sick = [m for m in pool if m not in set(healthy)]
    healthy.sort(key=strength_key)
    sick.sort(key=strength_key)

    ordered: list[str] = []
    seen: set[str] = set()
    for group in (healthy, sick):
        for pref in _VISION_STRENGTH_PIN:
            hit = next((m for m in group if m.lower() == pref.lower() and m not in seen), None)
            if hit:
                ordered.append(hit)
                seen.add(hit)
        for m in group:
            if m not in seen:
                ordered.append(m)
                seen.add(m)
    return ordered


def model_speed_tier(model: str, median_latency_ms: float | None) -> float:
    if median_latency_ms is not None and median_latency_ms > 0:
        # Successful calls only; 8s feels fast, 45s+ feels slow for routing.
        return max(0.08, min(1.0, 1.0 - (median_latency_ms / 45000.0)))
    if _SPEED_FAST.search(model or ""):
        return 0.88
    if _ACCURACY_ULTRA.search(model or ""):
        return 0.25
    if _ACCURACY_HIGH.search(model or ""):
        return 0.42
    return 0.58


def _normalize_route(client_model: str | None) -> str:
    raw = str(client_model or "").strip()
    if not raw or raw == "probe":
        return ""
    for cn, keys in ROUTE_ALIASES.items():
        if raw in keys or raw.lower() in {k.lower() for k in keys}:
            return cn
    return raw


def _usage_files() -> list[Path]:
    files: list[Path] = []
    if USAGE_PATH.exists():
        files.append(USAGE_PATH)
    files.extend(sorted(DATA_DIR.glob("usage-*.jsonl"), key=lambda p: p.stat().st_mtime))
    return files


def load_usage_stats() -> tuple[dict[str, Stat], dict[tuple[str, str], Stat]]:
    global_stats: dict[str, Stat] = defaultdict(Stat)
    route_stats: dict[tuple[str, str], Stat] = defaultdict(Stat)
    for path in _usage_files():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            model = apply_alias(str(row.get("model") or row.get("upstream_model") or ""))
            if not model:
                continue
            ok = bool(row.get("ok"))
            lat = row.get("latency_ms")
            try:
                latency = float(lat) if lat is not None else None
            except (TypeError, ValueError):
                latency = None
            global_stats[model].add(ok, latency)
            route_cn = _normalize_route(str(row.get("client_model") or row.get("route") or ""))
            if route_cn:
                route_stats[(route_cn, model)].add(ok, latency)
    return global_stats, route_stats


def _provider_tier_boost(p: dict[str, Any]) -> float:
    """daily > signup > free：重建路由时抬高日额度渠道权重。"""
    t = str(p.get("quota_tier") or "").strip().lower()
    if t == "daily":
        return 1.35
    if t == "signup":
        return 1.15
    if t == "free":
        return 0.55
    try:
        w = float(p.get("weight") or 1)
    except (TypeError, ValueError):
        w = 1.0
    if bool(p.get("free_only")) and w <= 5:
        return 0.55
    return 1.0


def _enabled_models(providers: list[dict[str, Any]] | None = None) -> list[str]:
    providers = providers if providers is not None else load_providers()
    ranked: list[tuple[float, str]] = []
    seen: set[str] = set()
    for p in sorted(
        providers,
        key=lambda x: float(x.get("weight") or 1) * _provider_tier_boost(x),
        reverse=True,
    ):
        if not p.get("enabled", True):
            continue
        key = str(p.get("api_key") or "").strip()
        if not key or key.startswith("REPLACE_") or "change-me" in key.lower():
            continue
        disabled = {str(x) for x in (p.get("disabled_models") or [])}
        weight = float(p.get("weight") or 1) * _provider_tier_boost(p)
        for m in p.get("models") or []:
            s = apply_alias(str(m))
            if not s or s in disabled or s in seen or is_non_chat_model(s):
                continue
            seen.add(s)
            ranked.append((weight * (0.45 if _is_free_fallback_model(s) else 1.0), s))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [m for _, m in ranked]


_NOVEL_PREF_PATTERNS: dict[str, re.Pattern[str]] = {
    "doubao": re.compile(r"doubao|seed-1-6|ep-", re.I),
    "hunyuan": re.compile(r"hunyuan", re.I),
    "nvidia": re.compile(r"nvidia/|nemotron|llama-3", re.I),
}


def _apply_novel_preference(
    pool: list[str],
    providers: list[dict[str, Any]],
    pref: str,
) -> list[str]:
    key = (pref or "auto").strip().lower()
    if key in {"", "auto"}:
        return pool
    pat = _NOVEL_PREF_PATTERNS.get(key)
    if not pat:
        return pool
    preferred: list[str] = []
    seen: set[str] = set()
    for m in pool:
        if pat.search(m):
            preferred.append(m)
            seen.add(m)
    for p in providers:
        pname = str(p.get("name") or "")
        if not pat.search(pname):
            continue
        for m in p.get("models") or []:
            sm = apply_alias(str(m))
            if sm in pool and sm not in seen:
                preferred.append(sm)
                seen.add(sm)
    if not preferred:
        return pool
    tail = [m for m in pool if m not in seen]
    return preferred + tail


def _novel_pool_filter(
    pool: list[str],
    global_stats: dict[str, Stat],
    route_stats: dict[tuple[str, str], Stat],
) -> list[str]:
    out: list[str] = []
    for m in pool:
        if _NOVEL_AVOID.search(m):
            continue
        rs = route_stats.get(("小说", m))
        if rs and rs.total >= 5 and rs.rate < 0.25:
            continue
        if _blacklisted(m, global_stats):
            continue
        out.append(m)
    if not out:
        out = [m for m in _NOVEL_PIN if m in pool] or list(pool[:6])
    pinned: list[str] = []
    seen: set[str] = set()
    for m in _NOVEL_PIN:
        if m in out and m not in seen:
            pinned.append(m)
            seen.add(m)
    for m in out:
        if m not in seen:
            pinned.append(m)
            seen.add(m)
    return pinned


def _blacklisted(model: str, global_stats: dict[str, Stat]) -> bool:
    st = global_stats.get(model)
    if not st or st.total < MIN_CALLS_BLACKLIST:
        return False
    return st.rate < MIN_SUCCESS_BLACKLIST


def _reliability_score(
    model: str,
    route_cn: str,
    heuristic_rank: float,
    global_stats: dict[str, Stat],
    route_stats: dict[tuple[str, str], Stat],
) -> float:
    rs = route_stats.get((route_cn, model))
    gs = global_stats.get(model)
    if rs and rs.total >= 2:
        base = rs.rate * 0.75 + (gs.rate if gs and gs.total else 0.5) * 0.25
        base += min(0.08, rs.total * 0.002)
        return min(1.0, base)
    if gs and gs.total >= 3:
        return min(1.0, gs.rate * 0.85 + heuristic_rank * 0.15)
    return 0.35 + heuristic_rank * 0.65


def _composite_score(
    model: str,
    route_cn: str,
    profile: RouteProfile,
    heuristic_rank: float,
    global_stats: dict[str, Stat],
    route_stats: dict[tuple[str, str], Stat],
) -> float:
    rel = _reliability_score(model, route_cn, heuristic_rank, global_stats, route_stats)
    gs = global_stats.get(model)
    rs = route_stats.get((route_cn, model))
    lat_src = rs if rs and rs.latencies_ms else gs
    spd = model_speed_tier(model, lat_src.median_latency_ms if lat_src else None)
    acc = model_accuracy_tier(model)
    w_sum = profile.reliability_w + profile.accuracy_w + profile.speed_w
    if w_sum <= 0:
        w_sum = 1.0
    score = (
        rel * profile.reliability_w
        + acc * profile.accuracy_w
        + spd * profile.speed_w
    ) / w_sum
    # Penalize models below route minimum accuracy bar (except when pool is tiny).
    if profile.min_accuracy > 0 and acc < profile.min_accuracy:
        score *= max(0.15, acc / profile.min_accuracy)
    return score


def pick_candidates(
    pool: list[str],
    profile: RouteProfile,
    global_stats: dict[str, Stat],
    route_stats: dict[tuple[str, str], Stat],
    *,
    top_n: int = TOP_N,
) -> list[str]:
    if not pool:
        return []
    route_cn = profile.cn
    scored: list[tuple[float, str]] = []
    n = max(1, len(pool))
    for i, model in enumerate(pool):
        if _blacklisted(model, global_stats):
            continue
        hr = 1.0 - (i / n)
        scored.append(
            (
                _composite_score(model, route_cn, profile, hr, global_stats, route_stats),
                model,
            )
        )
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Prefer models meeting min_accuracy; fall back if not enough.
    strict = [
        m
        for _, m in scored
        if profile.min_accuracy <= 0 or model_accuracy_tier(m) >= profile.min_accuracy
    ]
    picked = strict[:top_n] if len(strict) >= min(3, top_n) else [m for _, m in scored[:top_n]]

    if len(picked) < min(top_n, len(pool)):
        for m in pool:
            if m in picked or _blacklisted(m, global_stats):
                continue
            picked.append(m)
            if len(picked) >= top_n:
                break
    # Preserve order while removing duplicates.
    seen: set[str] = set()
    deduped: list[str] = []
    for m in picked:
        if m in seen:
            continue
        seen.add(m)
        deduped.append(m)
    if not deduped and pool:
        deduped = list(pool[:top_n])
    return deduped[:top_n]


def build_smart_routers(
    providers: list[dict[str, Any]] | None = None,
    *,
    top_n: int = TOP_N,
) -> dict[str, Any]:
    providers = providers if providers is not None else load_providers()
    all_models = _enabled_models(providers)
    global_stats, route_stats = load_usage_stats()
    routers: dict[str, Any] = {}

    for profile in PROFILES:
        pool = [m for m in all_models if profile.matcher(m)]
        if profile.cn == "日常" and len(pool) < 3:
            pool = list(all_models)
        if not pool:
            pool = list(all_models[: max(top_n, 6)])
        if profile.cn == "小说":
            pref = str(load_config().get("novel_preferred_provider") or "auto")
            pin = [m for m in _NOVEL_PIN if m in all_models]
            extra = [
                m
                for m in all_models
                if m not in pin and re.search(r"122b|235b|80b|flash", m, re.I) and not _NOVEL_AVOID.search(m)
            ]
            pool = _novel_pool_filter(pin + extra, global_stats, route_stats)
            pool = _apply_novel_preference(pool, providers, pref)
        if profile.cn == "识图":
            # 先按「当前可用 + 强度」排池，再打分；最后再钉一次顺序，避免弱但稳的挤掉强 VL。
            pool = _apply_vision_preference(pool, providers)
        if profile.cn in {"日常", "复杂", "推理", "代码", "长文"}:
            # 日额度/强模型优先，免费小杯与 :free 池垫底。
            pool = _apply_quality_then_free(pool)
        if profile.cn == "Agent":
            # 工具/Ardot 任务：严格按 PIN，不要被 VL/用量分打乱。
            pool = _apply_agent_preference(pool)
            cands = pool[:top_n]
        else:
            cands = pick_candidates(pool, profile, global_stats, route_stats, top_n=top_n)
        if profile.cn in {"日常", "复杂", "推理", "代码", "长文"}:
            cands = _apply_quality_then_free(cands)[:top_n]
            # 强制留 2～3 个免费小杯/池作末尾兜底（额度打满或大杯失败时）。
            free_tail = [
                m
                for m in _apply_quality_then_free(pool)
                if _is_free_fallback_model(m) and m not in cands
            ][:3]
            if free_tail:
                keep = max(0, top_n - len(free_tail))
                cands = cands[:keep] + free_tail
        if profile.cn == "识图":
            cands = _apply_vision_preference(cands, providers)[:top_n]
        if profile.cn == "小说":
            # Novel: fewer hops, only proven models (max 6).
            cands = cands[: min(6, top_n)]
        meta = {
            "description": profile.description,
            "candidates": cands,
            "built_at": int(time.time()),
            "top_n": top_n,
            "weights": {
                "reliability": profile.reliability_w,
                "accuracy": profile.accuracy_w,
                "speed": profile.speed_w,
            },
        }
        routers[profile.cn] = meta
        routers[profile.en] = {
            **meta,
            "description": profile.description + " (en)",
        }

    if "长文" in routers:
        routers["256k"] = {**routers["长文"], "description": "长上下文（同长文优选）"}
        routers["1m"] = {**routers["长文"], "description": "超长上下文（同长文优选）"}
    if "日常" in routers:
        routers["auto"] = {**routers["日常"], "description": "同日常（快+准均衡优选）"}

    return routers


def rebuild_and_save(
    providers: list[dict[str, Any]] | None = None,
    *,
    top_n: int = TOP_N,
) -> dict[str, Any]:
    try:
        from .channel_store import apply_to_state
        from .state import STATE

        apply_to_state(STATE)
    except Exception:
        pass
    routers = build_smart_routers(providers, top_n=top_n)
    save_routers(routers)
    summary = []
    for profile in PROFILES:
        cands = (routers.get(profile.cn) or {}).get("candidates") or []
        summary.append(
            {
                "route": profile.cn,
                "count": len(cands),
                "top": cands[:3],
                "weights": {
                    "reliability": profile.reliability_w,
                    "accuracy": profile.accuracy_w,
                    "speed": profile.speed_w,
                },
            }
        )
    return {
        "ok": True,
        "routes": routers,
        "summary": summary,
        "top_n": top_n,
        "usage_files": [str(p) for p in _usage_files()],
    }
