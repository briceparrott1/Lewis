from typing import Protocol

from anthropic import AsyncAnthropic

from lewis_api.config import get_settings


class LLM(Protocol):
    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict: ...


class AnthropicLLM:
    def __init__(self, client: AsyncAnthropic | None = None, model: str | None = None):
        settings = get_settings()
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.agent_model

    async def structured(
        self, system: str, user: str, tool_name: str, schema: dict
    ) -> dict:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[
                {"name": tool_name, "description": tool_name, "input_schema": schema}
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in resp.content:
            if block.type == "tool_use":
                return dict(block.input)
        return {}
