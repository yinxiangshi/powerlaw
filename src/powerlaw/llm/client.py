from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.config import Settings, get_settings
from powerlaw.models.tables import LlmCall


class LlmDisabledError(RuntimeError):
    pass


class OpenAIClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    async def call_text(
        self,
        session: AsyncSession,
        *,
        document_id: UUID | None,
        segment_id: UUID | None,
        purpose: str,
        prompt_version: str,
        prompt: str,
    ) -> tuple[str, dict[str, Any]]:
        if not self.settings.openai_api_key:
            raise LlmDisabledError("OPENAI_API_KEY is required for LLM calls")

        from openai import AsyncOpenAI

        started = time.perf_counter()
        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.responses.create(
            model=self.settings.openai_model,
            input=prompt,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response_payload = response.model_dump(mode="json")
        output_text = getattr(response, "output_text", None) or extract_response_text(
            response_payload
        )
        response_payload["_output_text"] = output_text
        usage = response.usage
        llm_call = LlmCall(
            document_id=document_id,
            segment_id=segment_id,
            purpose=purpose,
            model=self.settings.openai_model,
            prompt_version=prompt_version,
            prompt=prompt,
            response=response_payload,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=latency_ms,
        )
        session.add(llm_call)
        await session.flush()
        response_payload["_llm_call_id"] = str(llm_call.id)
        return output_text.strip(), response_payload

    async def call_json(
        self,
        session: AsyncSession,
        *,
        document_id: UUID | None,
        segment_id: UUID | None,
        purpose: str,
        prompt_version: str,
        prompt: str,
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise LlmDisabledError("OPENAI_API_KEY is required for LLM calls")

        from openai import AsyncOpenAI

        started = time.perf_counter()
        client = AsyncOpenAI(api_key=self.settings.openai_api_key)
        response = await client.responses.create(
            model=self.settings.openai_model,
            input=prompt,
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        response_payload = response.model_dump(mode="json")
        usage = response.usage
        llm_call = LlmCall(
            document_id=document_id,
            segment_id=segment_id,
            purpose=purpose,
            model=self.settings.openai_model,
            prompt_version=prompt_version,
            prompt=prompt,
            response=response_payload,
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
            latency_ms=latency_ms,
        )
        session.add(llm_call)
        await session.flush()
        response_payload["_llm_call_id"] = str(llm_call.id)
        return response_payload


def extract_response_text(response_payload: dict[str, Any]) -> str:
    direct = response_payload.get("output_text")
    if isinstance(direct, str):
        return direct

    chunks: list[str] = []
    for output_item in response_payload.get("output", []):
        if not isinstance(output_item, dict):
            continue
        for content_item in output_item.get("content", []):
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str):
                chunks.append(text)
            elif isinstance(text, dict) and isinstance(text.get("value"), str):
                chunks.append(text["value"])
    return "\n".join(chunk for chunk in chunks if chunk).strip()


LlmClient = OpenAIClient
