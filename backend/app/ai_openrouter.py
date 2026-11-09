"""Paid Gemini through OpenRouter BYOK, prepared but blocked for live use.

The router's translated input cannot yet be counted with a documented bound.
Only tests substitute count_input. Do not activate by changing a flag alone.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation

import httpx

from app.ai_content import AIUnavailable, BriefOutput, validate_content
from app.ai_diagnostics import provider_diagnostics
from app.ai_gemini import (
    INPUT_NANO_USD,
    INPUT_TOKENS,
    OUTPUT_NANO_USD,
    OUTPUT_TOKENS,
    RESERVATION_NANO_USD,
    messages_for,
)
from app.config import Settings

MODEL = "google/gemini-3.1-flash-lite"
PROVIDER = "google-ai-studio"
BASE_URL = "https://openrouter.ai/api/v1"
# Reserve the documented 5% BYOK fee even when a workspace has a free allowance.
BYOK_RESERVATION_NANO_USD = RESERVATION_NANO_USD * 105 // 100
LIVE_CONTRACT_VERIFIED = False


def payload_for(articles: list[dict]) -> dict:
    return {
        "model": MODEL,
        "messages": messages_for(articles),
        "max_tokens": OUTPUT_TOKENS,
        "reasoning": {"effort": "minimal", "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "news_brief",
                "strict": True,
                "schema": BriefOutput.model_json_schema(),
            },
        },
        "stream": False,
        "provider": {
            "only": [PROVIDER],
            "order": [PROVIDER],
            "ignore": [PROVIDER + "/flex", PROVIDER + "/priority"],
            "allow_fallbacks": False,
            "require_parameters": True,
            # These do NOT enforce BYOK-only: the workspace setting must also be checked.
        },
    }


def validate_usage(data: dict, counted: int) -> None:
    try:
        usage = data["usage"]
        prompt, completion, total = (
            usage[k] for k in ("prompt_tokens", "completion_tokens", "total_tokens")
        )
        reasoning = usage["completion_tokens_details"]["reasoning_tokens"]
        if (
            data["model"] != MODEL
            or data["provider"] != "Google AI Studio"
            or usage["is_byok"] is not True
        ):
            raise ValueError
        if not all(type(v) is int and v >= 0 for v in (prompt, completion, total, reasoning)):
            raise ValueError
        # OpenRouter completion_tokens already includes reasoning; do not add it twice.
        if not 0 < prompt <= counted <= INPUT_TOKENS or not 0 < completion <= OUTPUT_TOKENS:
            raise ValueError
        if reasoning > completion or total != prompt + completion:
            raise ValueError
        for details, names in (
            (
                "prompt_tokens_details",
                ("cached_tokens", "cache_write_tokens", "audio_tokens", "video_tokens"),
            ),
            ("completion_tokens_details", ("audio_tokens", "image_tokens")),
        ):
            for name in names:
                value = usage.get(details, {}).get(name, 0)
                if type(value) is not int or value != 0:
                    raise ValueError
        # Parse JSON decimals exactly. Never apply the former free-route cost == 0 rule.
        upstream = usage["cost_details"]["upstream_inference_cost"]
        fee = usage["cost"]
        if any(type(v) not in (int, Decimal) for v in (upstream, fee)):
            raise ValueError
        upstream, fee = Decimal(upstream), Decimal(fee)
        if not all(v.is_finite() and v >= 0 for v in (upstream, fee)):
            raise ValueError
        expected_nano = prompt * INPUT_NANO_USD + completion * OUTPUT_NANO_USD
        if upstream * 1_000_000_000 > expected_nano or fee > upstream * Decimal("0.05"):
            raise ValueError
        if (upstream + fee) * 1_000_000_000 > BYOK_RESERVATION_NANO_USD:
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation):
        raise AIUnavailable(
            "safety_stop", diagnostics={"contract_issue": "usage_or_model_mismatch"}
        ) from None


def validate_output(data: dict, articles: list[dict], counted: int) -> dict:
    validate_usage(data, counted)
    try:
        choices = data["choices"]
        if len(choices) != 1:
            raise ValueError
        choice = choices[0]
        if choice["finish_reason"] != "stop":
            raise AIUnavailable("invalid_output", 3600, {"output_issue": "incomplete_response"})
        message = choice["message"]
        if message.get("tool_calls") or message.get("function_call") or message.get("refusal"):
            raise ValueError
        if not isinstance(message["content"], str):
            raise ValueError
        return validate_content(message["content"], articles)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AIUnavailable("invalid_output", 3600, {"output_issue": "response_shape"}) from None


class OpenRouterBYOK:
    model = MODEL
    reservation_nano_usd = BYOK_RESERVATION_NANO_USD

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings, self.transport = settings, transport

    @property
    def activation_blocked(self) -> bool:
        return not LIVE_CONTRACT_VERIFIED

    @property
    def enabled(self) -> bool:
        return bool(
            LIVE_CONTRACT_VERIFIED
            and self.settings.ai_briefs_enabled
            and self.settings.ai_digest_enabled
            and self.settings.ai_privacy_reviewed
            and self.settings.openrouter_api_key
            and self.settings.openrouter_api_key.get_secret_value().strip()
        )

    async def preflight(self) -> None:
        if not self.enabled:
            raise AIUnavailable("activation_required" if self.activation_blocked else "disabled")

    async def count_input(self, body: dict) -> int:
        # No documented pre-generation counter for this translated request, including schema.
        # A native Google count or a character estimate cannot establish that bound.
        raise AIUnavailable("activation_required")

    async def _request(self, body: dict, counted: int) -> dict:
        await self.preflight()
        diagnostics = {}
        try:
            async with asyncio.timeout(25):
                async with httpx.AsyncClient(
                    base_url=BASE_URL,
                    transport=self.transport,
                    timeout=20,
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.openrouter_api_key.get_secret_value()
                    },
                ) as client:
                    async with client.stream("POST", "/chat/completions", json=body) as response:
                        diagnostics = provider_diagnostics(
                            response.status_code, response.headers.get("Retry-After")
                        )
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 100_000:
                                raise AIUnavailable(
                                    "safety_stop",
                                    diagnostics={"contract_issue": "oversized_response"},
                                )
                        try:
                            data = json.loads(raw, parse_float=Decimal)
                        except (ValueError, InvalidOperation):
                            data = None
                        if isinstance(data, dict) and "usage" in data:
                            validate_usage(data, counted)
                        if response.status_code == 429:
                            raise AIUnavailable(
                                "temporary_limit",
                                max(60, diagnostics.get("retry_after_seconds", 3600)),
                            )
                        if response.status_code in {400, 404, 422}:
                            raise AIUnavailable("model_unavailable", 3600)
                        if response.status_code != 200:
                            raise AIUnavailable("provider_unavailable", 3600)
                        if not isinstance(data, dict) or "error" in data:
                            raise AIUnavailable(
                                "safety_stop", diagnostics={"contract_issue": "invalid_envelope"}
                            )
                        return data
        except AIUnavailable as exc:
            exc.diagnostics = {**diagnostics, **exc.diagnostics}
            raise
        except (httpx.HTTPError, TimeoutError):
            raise AIUnavailable("uncertain", 3600, diagnostics) from None

    async def generate(
        self, articles: list[dict], *, before_generate: Callable[[], Awaitable[object]]
    ) -> dict:
        await self.preflight()
        body = payload_for(articles)
        counted = await self.count_input(body)
        if type(counted) is not int or counted <= 0:
            raise AIUnavailable(
                "safety_stop", diagnostics={"contract_issue": "invalid_token_count"}
            )
        if counted > INPUT_TOKENS:
            raise AIUnavailable("input_limit", 3600)
        await before_generate()
        return validate_output(await self._request(body, counted), articles, counted)
