from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .constants import DEFAULT_MODEL, MODEL_OPTIONS


OPENAI_PROVIDER_KEY = "openai"
DEEPSEEK_PROVIDER_KEY = "deepseek"
DEFAULT_PROVIDER_KEY = OPENAI_PROVIDER_KEY


@dataclass(frozen=True)
class ProviderProfile:
    key: str
    label: str
    base_url: Optional[str]
    model_options: dict[str, str]
    default_model: str
    transport: str
    reasoning_options: Optional[dict[str, str]] = None
    default_reasoning_effort: str = "none"


PROVIDER_PROFILES = {
    OPENAI_PROVIDER_KEY: ProviderProfile(
        key=OPENAI_PROVIDER_KEY,
        label="OpenAI",
        base_url=None,
        model_options=MODEL_OPTIONS,
        default_model=DEFAULT_MODEL,
        transport="chat_completions",
    ),
    DEEPSEEK_PROVIDER_KEY: ProviderProfile(
        key=DEEPSEEK_PROVIDER_KEY,
        label="DeepSeek",
        base_url="https://api.deepseek.com",
        model_options={
            "DeepSeek Flash": "deepseek-flash",
            "DeepSeek V4 Pro": "deepseek-v4-pro",
            "Custom": "",
        },
        default_model="deepseek-flash",
        transport="responses",
        reasoning_options={
            "Off (lowest cost)": "none",
            "Low": "low",
            "High": "high",
            "Maximum": "max",
        },
        default_reasoning_effort="none",
    ),
}


def provider_options() -> dict[str, str]:
    return {provider.label: provider.key for provider in PROVIDER_PROFILES.values()}


def get_provider(provider_key: Optional[str]) -> ProviderProfile:
    return PROVIDER_PROFILES.get(provider_key or DEFAULT_PROVIDER_KEY, PROVIDER_PROFILES[DEFAULT_PROVIDER_KEY])
