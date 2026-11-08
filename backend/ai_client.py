"""Shared OpenAI-compatible client settings for direct OpenAI or OpenRouter."""

import os
from urllib.parse import urlparse

from openai import OpenAI


def model_name(name: str) -> str:
    if urlparse(os.getenv("OPENAI_BASE_URL", "")).hostname == "openrouter.ai" and "/" not in name:
        return f"openai/{name}"
    return name


def make_client(**kwargs) -> OpenAI:
    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)
