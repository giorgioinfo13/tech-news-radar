"""Fixed paid Gemini adapter with an explicitly accepted prudential budget.

Only the service's durable dispatch guard may authorize generation. No SDK, tools,
remote cache, automatic retry, continuation, model alias, or provider fallback.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable

import httpx

from app.ai_content import SYSTEM, AIUnavailable, BriefOutput, validate_content
from app.ai_diagnostics import provider_diagnostics
from app.config import Settings

MODEL = "gemini-3.1-flash-lite"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
INPUT_TOKENS = 3500
OUTPUT_TOKENS = 500
# Exact integer nano-USD. Standard text rates verified 2026-11-09: $0.25 / $1.50 per million tokens.
INPUT_NANO_USD = 250
OUTPUT_NANO_USD = 1500
RESERVATION_NANO_USD = INPUT_TOKENS * INPUT_NANO_USD + OUTPUT_TOKENS * OUTPUT_NANO_USD
MONTHLY_NANO_USD = 2_000_000_000
# Reservation estimate: countTokens does not establish a complete billable-input bound.
# See docs/ai-briefs.md. Observed anomalies still stop further work persistently.
MAX_PROMPT_BYTES = 24_000
BUDGET_MESSAGE = (
    "Budget mensile locale di 2,00 USD esaurito. Le rassegne salvate restano disponibili."
)


def messages_for(articles: list[dict]) -> list[dict]:
    """Bound resources only. Bytes/characters are never used as a token guarantee."""
    content = (
        json.dumps(
            [{key: a[key] for key in ("id", "title", "description")} for a in articles],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        .replace("<", r"\u003c")
        .replace(">", r"\u003e")
    )
    if len(articles) > 12 or len(content.encode()) > MAX_PROMPT_BYTES:
        raise AIUnavailable("insufficient_material")
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}]


def payload_for(articles: list[dict]) -> dict:
    messages = messages_for(articles)
    return {
        "systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
        "contents": [{"role": "user", "parts": [{"text": messages[1]["content"]}]}],
        "generationConfig": {
            "candidateCount": 1,
            "maxOutputTokens": OUTPUT_TOKENS,
            "thinkingConfig": {"thinkingLevel": "MINIMAL", "includeThoughts": False},
            "responseFormat": {
                "text": {"mimeType": "APPLICATION_JSON", "schema": BriefOutput.model_json_schema()}
            },
        },
    }


def validate_usage(data: dict, counted: int) -> dict:
    """Post-response circuit breaker, not a retroactive billing guarantee."""
    usage = data.get("usageMetadata")
    diagnostics = {}
    if isinstance(usage, dict):
        for source, target in {
            "promptTokenCount": "input_tokens",
            "candidatesTokenCount": "output_tokens",
            "thoughtsTokenCount": "thought_tokens",
            "totalTokenCount": "total_tokens",
        }.items():
            value = usage.get(source)
            if type(value) is int and 0 <= value <= 10_000_000:
                diagnostics[target] = value
    diagnostics["model_matches"] = int(data.get("modelVersion") == MODEL)
    if type(counted) is int and 0 <= counted <= 10_000_000:
        diagnostics["counted_tokens"] = counted

    def reject(issue: str) -> None:
        raise AIUnavailable("safety_stop", diagnostics={**diagnostics, "contract_issue": issue})

    if not diagnostics["model_matches"]:
        reject("model_mismatch")
    if not isinstance(usage, dict):
        reject("invalid_usage")
    diagnostics["thoughts_missing"] = int("thoughtsTokenCount" not in usage)
    prompt = usage.get("promptTokenCount")
    visible = usage.get("candidatesTokenCount")
    total = usage.get("totalTokenCount")
    # Google makes this field optional. Omission is accepted as zero ONLY when
    # the mandatory total reconciles exactly; null/bool/negative remain invalid.
    thoughts = usage.get("thoughtsTokenCount", 0)
    if not all(type(v) is int and v >= 0 for v in (prompt, visible, thoughts, total)):
        reject("invalid_usage")
    if type(counted) is not int or not 0 < prompt <= counted <= INPUT_TOKENS:
        reject("input_count_mismatch")
    if not 0 < visible + thoughts <= OUTPUT_TOKENS:
        reject("output_limit")
    if total != prompt + visible + thoughts:
        reject("total_mismatch")
    for name in ("cachedContentTokenCount", "toolUsePromptTokenCount"):
        value = usage.get(name, 0)
        if type(value) is not int or value != 0:
            reject("unexpected_cache_or_tools")
    for name in ("promptTokensDetails", "candidatesTokensDetails"):
        items = usage.get(name, [])
        if not isinstance(items, list) or any(
            not isinstance(item, dict) or item.get("modality") != "TEXT" for item in items
        ):
            reject("unexpected_modality")
    cost = prompt * INPUT_NANO_USD + (visible + thoughts) * OUTPUT_NANO_USD
    if cost > RESERVATION_NANO_USD:
        reject("reservation_exceeded")
    return {
        "input_tokens": prompt,
        "output_tokens": visible,
        "thought_tokens": thoughts,
        "total_tokens": total,
        "counted_tokens": counted,
        "usage_validated": 1,
        "estimated_nano_usd": cost,
    }


def validate_output(data: dict, articles: list[dict], counted: int) -> dict:
    diagnostic = validate_usage(data, counted)
    try:
        candidates = data["candidates"]
        if len(candidates) != 1:
            raise ValueError
        candidate = candidates[0]
        if candidate["finishReason"] != "STOP":
            raise AIUnavailable(
                "invalid_output", 3600, {**diagnostic, "output_issue": "incomplete_response"}
            )
        if candidate.get("groundingMetadata") or candidate.get("urlContextMetadata"):
            raise ValueError
        parts = candidate["content"]["parts"]
        if not parts or any(
            set(p) - {"text", "thoughtSignature"} or not isinstance(p.get("text"), str)
            for p in parts
        ):
            raise ValueError
        content = "".join(p["text"] for p in parts)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AIUnavailable(
            "invalid_output", 3600, {**diagnostic, "output_issue": "response_shape"}
        ) from None
    try:
        return {**validate_content(content, articles), "usage": diagnostic}
    except AIUnavailable as exc:
        exc.diagnostics = {**diagnostic, **exc.diagnostics}
        raise


class Gemini:
    model = MODEL
    reservation_nano_usd = RESERVATION_NANO_USD

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    @property
    def activation_blocked(self) -> bool:
        return not self.settings.ai_budget_risk_accepted

    @property
    def enabled(self) -> bool:
        return bool(
            self.settings.ai_budget_risk_accepted
            and self.settings.ai_briefs_enabled
            and self.settings.ai_digest_enabled
            and self.settings.ai_privacy_reviewed
            and self.settings.gemini_api_key
            and self.settings.gemini_api_key.get_secret_value().strip()
        )

    async def preflight(self) -> None:
        if not self.enabled:
            raise AIUnavailable("activation_required" if self.activation_blocked else "disabled")

    async def _request(self, operation: str, body: dict, *, counted: int | None = None) -> dict:
        await self.preflight()
        if operation not in {"countTokens", "generateContent"}:
            raise AIUnavailable("disabled")
        if operation == "generateContent" and (
            type(counted) is not int or not 0 < counted <= INPUT_TOKENS
        ):
            raise AIUnavailable(
                "safety_stop", diagnostics={"contract_issue": "invalid_token_count"}
            )
        diagnostics = {}
        try:
            async with asyncio.timeout(5 if operation == "countTokens" else 25):
                async with httpx.AsyncClient(
                    base_url=BASE_URL,
                    transport=self.transport,
                    follow_redirects=False,
                    trust_env=False,
                    timeout=20,
                    headers={"x-goog-api-key": self.settings.gemini_api_key.get_secret_value()},
                ) as client:
                    async with client.stream(
                        "POST", f"/models/{MODEL}:{operation}", json=body
                    ) as response:
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
                            data = json.loads(raw)
                        except ValueError:
                            data = None
                        if response.status_code != 200 or (
                            isinstance(data, dict) and "error" in data
                        ):
                            if isinstance(data, dict) and "usageMetadata" in data:
                                # Errors must obey the same measured bound as successful output.
                                diagnostics.update(
                                    validate_usage(data, counted if counted is not None else 0)
                                )
                            if response.status_code == 200:
                                raise AIUnavailable(
                                    "safety_stop",
                                    diagnostics={"contract_issue": "invalid_envelope"},
                                )
                            if response.status_code == 429:
                                raise AIUnavailable(
                                    "temporary_limit",
                                    max(60, diagnostics.get("retry_after_seconds", 3600)),
                                )
                            if response.status_code in {400, 404, 422}:
                                raise AIUnavailable("model_unavailable", 3600)
                            raise AIUnavailable("provider_unavailable", 3600)
                        if not isinstance(data, dict) or "error" in data:
                            raise AIUnavailable(
                                "safety_stop",
                                diagnostics={"contract_issue": "invalid_envelope"},
                            )
                        return data
        except AIUnavailable as exc:
            exc.diagnostics = {**diagnostics, **exc.diagnostics}
            raise
        except (httpx.HTTPError, TimeoutError):
            raise AIUnavailable("uncertain", 3600, diagnostics) from None

    async def generate(
        self, articles: list[dict], *, before_generate: Callable[[int], Awaitable[object]]
    ) -> dict:
        body = payload_for(articles)
        # Includes systemInstruction and generationConfig in the same request.
        # Passing schema is NOT proof of full billable coverage; acceptance is required.
        count = await self._request(
            "countTokens", {"generateContentRequest": {"model": f"models/{MODEL}", **body}}
        )
        measured = count.get("totalTokens")
        if type(measured) is not int or measured <= 0:
            raise AIUnavailable(
                "safety_stop", diagnostics={"contract_issue": "invalid_token_count"}
            )
        if measured > INPUT_TOKENS:
            raise AIUnavailable("input_limit", 3600, {"counted_tokens": measured})
        # Recheck revocation, clock, lease and persistent one-time dispatch after token counting.
        try:
            await before_generate(measured)
            data = await self._request("generateContent", body, counted=measured)
            return validate_output(data, articles, measured)
        except AIUnavailable as exc:
            exc.diagnostics = {"counted_tokens": measured, **exc.diagnostics}
            raise
