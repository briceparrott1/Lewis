import pytest

from lewis_api.main import app, lifespan


@pytest.mark.asyncio
async def test_lifespan_builds_agent_graph_without_langfuse_configured():
    async with lifespan(app):
        assert app.state.agent_graph is not None
