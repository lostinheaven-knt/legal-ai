from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from legal_ai.llm.prompts import PromptContract


class MissingProviderConfig(RuntimeError):
    """Raised when DeepSeek-compatible provider settings are incomplete."""


class LLMProviderError(RuntimeError):
    """Raised when the provider returns an error response."""


class LLMTimeoutError(RuntimeError):
    """Raised when the provider request times out."""


class LLMInvalidJSONError(RuntimeError):
    """Raised when the provider response content is not valid JSON."""


class LLMSchemaValidationError(RuntimeError):
    """Raised when parsed JSON does not match the expected schema."""


@dataclass(frozen=True)
class ProviderSettings:
    api_key: str
    base_url: str
    model: str = "deepseek-chat"
    timeout_seconds: float = 45
    max_retries: int = 1

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


T = TypeVar("T", bound=BaseModel)


def provider_configured(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool(source.get("DEEPSEEK_API_KEY") and source.get("DEEPSEEK_BASE_URL"))


def settings_from_environment(
    env: Mapping[str, str] | None = None,
    *,
    model: str = "deepseek-chat",
    timeout_seconds: float = 45,
    max_retries: int = 1,
) -> ProviderSettings:
    source = os.environ if env is None else env
    api_key = source.get("DEEPSEEK_API_KEY")
    base_url = source.get("DEEPSEEK_BASE_URL")
    missing = [
        name
        for name, value in {
            "DEEPSEEK_API_KEY": api_key,
            "DEEPSEEK_BASE_URL": base_url,
        }.items()
        if not value
    ]
    if missing:
        raise MissingProviderConfig(f"Missing provider configuration: {', '.join(missing)}")
    return ProviderSettings(
        api_key=str(api_key),
        base_url=str(base_url),
        model=model,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


def redact_secrets(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted


class LLMClient:
    def __init__(
        self,
        settings: ProviderSettings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._transport = transport

    @classmethod
    def from_environment(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        model: str = "deepseek-chat",
        timeout_seconds: float = 45,
        max_retries: int = 1,
        transport: httpx.BaseTransport | None = None,
    ) -> "LLMClient":
        return cls(
            settings_from_environment(
                env,
                model=model,
                timeout_seconds=timeout_seconds,
                max_retries=max_retries,
            ),
            transport=transport,
        )

    def complete_json(
        self,
        prompt_contract: PromptContract,
        user_content: str,
        response_model: type[T],
    ) -> T:
        payload = self._build_payload(prompt_contract, user_content, response_model)
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                return self._post_and_validate(payload, headers, response_model)
            except LLMTimeoutError as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    raise
            except LLMProviderError:
                raise
        if last_error:
            raise last_error
        raise LLMProviderError("Provider request did not complete")

    def _build_payload(
        self,
        prompt_contract: PromptContract,
        user_content: str,
        response_model: type[BaseModel],
    ) -> dict[str, Any]:
        schema = json.dumps(response_model.model_json_schema(), ensure_ascii=False)
        return {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{prompt_contract.body}\n\n"
                        "Return only valid JSON matching this JSON Schema:\n"
                        f"{schema}\n\n"
                        "Do not include Markdown fences or explanatory text."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }

    def _post_and_validate(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        response_model: type[T],
    ) -> T:
        timeout = httpx.Timeout(self.settings.timeout_seconds)
        try:
            with httpx.Client(transport=self._transport, timeout=timeout) as client:
                response = client.post(self.settings.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise LLMTimeoutError("Provider request timed out") from exc
        except httpx.HTTPError as exc:
            message = redact_secrets(str(exc), [self.settings.api_key])
            raise LLMProviderError(message) from exc

        if response.status_code >= 400:
            message = redact_secrets(response.text, [self.settings.api_key])
            raise LLMProviderError(f"Provider returned HTTP {response.status_code}: {message}")

        content = self._extract_content(response)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMInvalidJSONError("Provider response content was not valid JSON") from exc

        try:
            return response_model.model_validate(parsed)
        except ValidationError as exc:
            raise LLMSchemaValidationError(str(exc)) from exc

    @staticmethod
    def _extract_content(response: httpx.Response) -> str:
        try:
            envelope = response.json()
            return str(envelope["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Provider response did not include chat completion content") from exc
