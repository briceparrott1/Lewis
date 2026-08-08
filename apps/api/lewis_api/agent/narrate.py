import json
from collections.abc import AsyncIterator

from lewis_api.agent.llm import LLM
from lewis_api.agent.state import RankedJob, StructuredPrefs

_SYSTEM = (
    "You are a friendly job-search assistant writing a short summary of search "
    "results directly to the user in a chat. Address them by name. Say how many "
    "jobs you found. Call out the top-ranked result by title and company and "
    "explain briefly why it fits, tying back to their resume or preferences. If "
    "another result is a bit of a stretch from what they asked for, mention it "
    "and say why it might still be worth a look. 2-4 sentences, conversational, "
    "no bullet points, no markdown."
)

_NO_RESULTS = (
    "I didn't find any roles matching that this time — try broadening your "
    "criteria (location, seniority, or role type) and I'll take another look."
)


def fallback_text(n: int) -> str:
    return f"I found {n} job{'s' if n != 1 else ''} matching your search."


def _compact(ranked: list[RankedJob]) -> list[dict]:
    return [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "score": j.get("score"),
            "reason": j.get("reason"),
        }
        for j in ranked
    ]


async def stream_narrative_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    resume_text: str,
    user_name: str | None,
    llm: LLM,
) -> AsyncIterator[str]:
    """Yields the narrative text as chunks arrive from the LLM. Raises on LLM
    failure — the caller (graph.py's respond node) falls back to
    fallback_text(), since by the time a mid-stream error can occur, earlier
    chunks may already be visible to the user."""
    if not ranked:
        yield _NO_RESULTS
        return
    user = (
        f"User's name: {user_name or 'there'}\n\n"
        f"Preferences: {json.dumps(prefs)}\n\n"
        f"Ranked results, best first:\n{json.dumps(_compact(ranked))}"
    )
    async for chunk in llm.stream(system=_SYSTEM, user=user):
        yield chunk
