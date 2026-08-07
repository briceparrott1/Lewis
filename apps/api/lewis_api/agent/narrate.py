import json

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


async def narrate_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    resume_text: str,
    user_name: str | None,
    llm: LLM,
) -> str:
    if not ranked:
        return _NO_RESULTS
    compact = [
        {
            "title": j.get("title"),
            "company": j.get("company"),
            "location": j.get("location"),
            "score": j.get("score"),
            "reason": j.get("reason"),
        }
        for j in ranked
    ]
    user = (
        f"User's name: {user_name or 'there'}\n\n"
        f"Preferences: {json.dumps(prefs)}\n\n"
        f"Ranked results, best first:\n{json.dumps(compact)}"
    )
    try:
        return await llm.complete(system=_SYSTEM, user=user)
    except Exception:  # noqa: BLE001
        n = len(ranked)
        return f"I found {n} job{'s' if n != 1 else ''} matching your search."
