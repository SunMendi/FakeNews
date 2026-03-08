from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from time import perf_counter

import requests
from google import genai
from google.genai import types


logger = logging.getLogger(__name__)


class LLMProviderError(Exception):
    pass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str


class LLMRouter:
    def __init__(self):
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
        self.groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b").strip()
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "").strip()

        self.gemini_client = genai.Client(api_key=self.gemini_key) if self.gemini_key else None

    def complete(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        expect_json: bool = False,
        max_output_tokens: int = 400,
        temperature: float = 0.1,
    ) -> LLMResponse:
        attempts = [
            ("gemini", self._call_gemini),
            ("groq", self._call_groq),
            ("openrouter", self._call_openrouter),
        ]

        last_error: Exception | None = None
        for provider_name, provider_fn in attempts:
            try:
                response = provider_fn(
                    task_name=task_name,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    expect_json=expect_json,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                )
                logger.info(
                    "llm_success task=%s provider=%s model=%s",
                    task_name,
                    response.provider,
                    response.model,
                )
                return response
            except LLMProviderError as exc:
                last_error = exc
                logger.warning("llm_fallback task=%s provider=%s reason=%s", task_name, provider_name, exc)

        raise LLMProviderError(
            f"All LLM providers failed for task={task_name}. last_error={last_error}"
        )

    def _call_gemini(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        expect_json: bool,
        max_output_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        if not self.gemini_client:
            raise LLMProviderError("missing GEMINI_API_KEY")

        started = perf_counter()
        try:
            response = self.gemini_client.models.generate_content(
                model=self.gemini_model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json" if expect_json else "text/plain",
                ),
            )
            text = (response.text or "").strip()
            if not text:
                raise LLMProviderError("empty response")
            logger.info(
                "llm_attempt task=%s provider=gemini model=%s duration_ms=%s",
                task_name,
                self.gemini_model,
                int((perf_counter() - started) * 1000),
            )
            return LLMResponse(text=text, provider="gemini", model=self.gemini_model)
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def _call_groq(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        expect_json: bool,
        max_output_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        if not self.groq_key:
            raise LLMProviderError("missing GROQ_API_KEY")

        started = perf_counter()
        payload = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if expect_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.groq_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=30,
            )
            if response.status_code >= 400:
                raise LLMProviderError(f"status={response.status_code} body={response.text[:500]}")
            data = response.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not text:
                raise LLMProviderError("empty response")
            logger.info(
                "llm_attempt task=%s provider=groq model=%s duration_ms=%s",
                task_name,
                self.groq_model,
                int((perf_counter() - started) * 1000),
            )
            return LLMResponse(text=text, provider="groq", model=self.groq_model)
        except requests.RequestException as exc:
            raise LLMProviderError(str(exc)) from exc

    def _call_openrouter(
        self,
        *,
        task_name: str,
        system_prompt: str,
        user_prompt: str,
        expect_json: bool,
        max_output_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        if not self.openrouter_key:
            raise LLMProviderError("missing OPENROUTER_API_KEY")

        started = perf_counter()
        payload = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if self.openrouter_model:
            payload["model"] = self.openrouter_model
        if expect_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://127.0.0.1:8000"),
                    "X-OpenRouter-Title": os.getenv("OPENROUTER_APP_NAME", "Fake News Detector"),
                },
                json=payload,
                timeout=30,
            )
            if response.status_code >= 400:
                raise LLMProviderError(f"status={response.status_code} body={response.text[:500]}")
            data = response.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not text:
                raise LLMProviderError("empty response")
            model_name = data.get("model") or self.openrouter_model or "default"
            logger.info(
                "llm_attempt task=%s provider=openrouter model=%s duration_ms=%s",
                task_name,
                model_name,
                int((perf_counter() - started) * 1000),
            )
            return LLMResponse(text=text, provider="openrouter", model=model_name)
        except requests.RequestException as exc:
            raise LLMProviderError(str(exc)) from exc


router = LLMRouter()


def complete_text(
    *,
    task_name: str,
    system_prompt: str,
    user_prompt: str,
    expect_json: bool = False,
    max_output_tokens: int = 400,
    temperature: float = 0.1,
) -> LLMResponse:
    return router.complete(
        task_name=task_name,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        expect_json=expect_json,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
