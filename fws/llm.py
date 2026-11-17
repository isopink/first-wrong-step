"""Thin wrapper over the Anthropic Messages API: images in, validated JSON out, usage counted."""

from __future__ import annotations

import copy
import json
import os
import time
from dataclasses import dataclass, field
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

# USD per million tokens, first-party API rates as of 2026-11.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}

DEFAULT_MODEL = os.environ.get("FWS_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.environ.get("FWS_EFFORT", "high")
USE_FALLBACKS = os.environ.get("FWS_FALLBACKS", "1") != "0"


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    seconds: float = 0.0
    by_model: dict = field(default_factory=dict)

    def add(self, model: str, u) -> None:
        self.calls += 1
        self.input_tokens += u.input_tokens
        self.output_tokens += u.output_tokens
        self.cache_read_tokens += getattr(u, "cache_read_input_tokens", 0) or 0
        m = self.by_model.setdefault(model, [0, 0])
        m[0] += u.input_tokens
        m[1] += u.output_tokens

    def cost_usd(self) -> float:
        total = 0.0
        for model, (i, o) in self.by_model.items():
            pin, pout = PRICES.get(model, (0.0, 0.0))
            total += i / 1e6 * pin + o / 1e6 * pout
        return round(total, 5)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "seconds": round(self.seconds, 2),
            "cost_usd": self.cost_usd(),
        }


def strict_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema made acceptable to structured outputs: every object closed, every field required."""
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node):
        if isinstance(node, dict):
            node.pop("default", None)
            node.pop("title", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


def image_block(b64: str, media_type: str = "image/jpeg") -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}}


def pdf_block(b64: str) -> dict:
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}


class LLM:
    def __init__(self, model: str = DEFAULT_MODEL, effort: str = DEFAULT_EFFORT, client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.client = client or anthropic.Anthropic()
        self.usage = Usage()

    def structured(self, system: str, content: list[dict], out: type[T], max_tokens: int = 16000, retries: int = 1) -> T:
        """One request whose reply must validate as `out`. Retries once on invalid JSON."""
        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": strict_schema(out)},
            },
        )
        last_err: Exception | None = None
        for _ in range(retries + 1):
            t0 = time.perf_counter()
            if USE_FALLBACKS:
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
                )
            else:
                resp = self.client.messages.create(**kwargs)
            self.usage.seconds += time.perf_counter() - t0
            self.usage.add(resp.model, resp.usage)

            if resp.stop_reason == "refusal":
                raise LLMError(f"model declined: {getattr(resp, 'stop_details', None)}")
            if resp.stop_reason == "max_tokens":
                last_err = LLMError("reply cut off at max_tokens")
                kwargs["max_tokens"] = min(max_tokens * 2, 64000)
                continue
            text = "".join(b.text for b in resp.content if b.type == "text")
            try:
                return out.model_validate(json.loads(text))
            except (json.JSONDecodeError, ValidationError) as e:
                last_err = e
        raise LLMError(f"no valid {out.__name__} after {retries + 1} tries: {last_err}")
