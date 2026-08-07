from typing import Protocol

from anthropic import AsyncAnthropic

from lewis_api.agent.tracing import observe_generation
from lewis_api.config import get_settings


class LLM(Protocol):
    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict: ...

    async def complete(self, system: str, user: str) -> str: ...


def _usage_details(resp) -> dict | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    return {"input": usage.input_tokens, "output": usage.output_tokens}


class AnthropicLLM:
    def __init__(self, client: AsyncAnthropic | None = None, model: str | None = None):
        settings = get_settings()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.agent_model

    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict:
        with observe_generation(
            tool_name, self._model, {"system": system, "user": user}
        ) as generation:
            resp = await self._client.messages.create(
                model=self._model,
                # Ranking ~50 jobs needs well over 1500 output tokens; a low cap
                # truncates the tool call and yields empty results. Billing is on
                # actual output, so a high ceiling is free insurance.
                max_tokens=8192,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[
                    {"name": tool_name, "description": tool_name, "input_schema": schema}
                ],
                tool_choice={"type": "tool", "name": tool_name},
            )
            result = {}
            for block in resp.content:
                if block.type == "tool_use":
                    result = dict(block.input)
                    break
            generation.update(output=result, usage_details=_usage_details(resp))
            return result

    async def complete(self, system: str, user: str) -> str:
        with observe_generation(
            "complete", self._model, {"system": system, "user": user}
        ) as generation:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            result = ""
            for block in resp.content:
                if block.type == "text":
                    result = block.text
                    break
            generation.update(output=result, usage_details=_usage_details(resp))
            return result
