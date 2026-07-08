from __future__ import annotations

from dataclasses import dataclass

from legal_ai.llm.client import (
    LLMInvalidJSONError,
    LLMProviderError,
    LLMSchemaValidationError,
    LLMTimeoutError,
    MissingProviderConfig,
)


LLM_COMMAND_EXCEPTIONS = (
    MissingProviderConfig,
    LLMProviderError,
    LLMTimeoutError,
    LLMInvalidJSONError,
    LLMSchemaValidationError,
)


@dataclass(frozen=True)
class ProductizedLLMError(RuntimeError):
    category: str
    message: str
    source_type: str

    def __str__(self) -> str:
        return f"{self.category}: {self.message}"


def map_llm_exception(exc: BaseException) -> ProductizedLLMError:
    if isinstance(exc, MissingProviderConfig):
        missing = _safe_missing_provider_config(str(exc))
        return ProductizedLLMError(
            category="llm_provider_config",
            message=(
                f"LLM provider configuration is missing: {missing}. "
                "Set the missing DeepSeek environment variables, or use --llm auto/off."
            ),
            source_type=type(exc).__name__,
        )
    if isinstance(exc, LLMTimeoutError):
        return ProductizedLLMError(
            category="llm_timeout",
            message=(
                "The LLM provider request timed out. Retry, increase the configured timeout, "
                "or use --llm auto/off."
            ),
            source_type=type(exc).__name__,
        )
    if isinstance(exc, LLMInvalidJSONError):
        return ProductizedLLMError(
            category="llm_invalid_response",
            message=(
                "The LLM provider returned non-JSON content. Retry, change model/provider, "
                "or use --llm auto/off."
            ),
            source_type=type(exc).__name__,
        )
    if isinstance(exc, LLMSchemaValidationError):
        return ProductizedLLMError(
            category="llm_schema_validation",
            message=(
                "The LLM provider response did not match the required schema. Retry, "
                "change model/provider, or use --llm auto/off."
            ),
            source_type=type(exc).__name__,
        )
    if isinstance(exc, LLMProviderError):
        return ProductizedLLMError(
            category="llm_provider_error",
            message=(
                "The LLM provider request failed. Check provider URL, credentials, "
                "service status, and retry, or use --llm auto/off."
            ),
            source_type=type(exc).__name__,
        )
    return ProductizedLLMError(
        category="llm_provider_error",
        message="The LLM provider request failed. Use --llm auto/off or retry later.",
        source_type=type(exc).__name__,
    )


def _safe_missing_provider_config(message: str) -> str:
    known_names = ["DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"]
    missing = [name for name in known_names if name in message]
    return ", ".join(missing or known_names)
