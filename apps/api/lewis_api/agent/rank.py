import json

from lewis_api.agent.llm import LLM
from lewis_api.agent.state import Job, RankedJob, StructuredPrefs

_SCHEMA = {
    "type": "object",
    "properties": {
        "rankings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "external_id": {"type": "string"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["external_id", "score", "reason"],
            },
        }
    },
    "required": ["rankings"],
}

_SYSTEM = (
    "Score each candidate job 0-100 for how well it fits the user's resume and "
    "preferences. Trade off soft preferences in the order given by 'priorities' "
    "(most important first); never violate a 'required' dimension. Give a concise "
    "one-line reason per job, citing tradeoffs where relevant."
)


async def rank_jobs(
    candidates: list[Job],
    prefs: StructuredPrefs,
    resume_text: str,
    llm: LLM,
) -> list[RankedJob]:
    compact = [
        {
            "external_id": c.get("external_id"),
            "title": c.get("title"),
            "company": c.get("company"),
            "location": c.get("location"),
            # 800 chars keeps ranking signal while holding down input cost across
            # ~50 candidates (title/company/location carry most of the signal).
            "description": (c.get("description") or "")[:800],
        }
        for c in candidates
    ]
    user = (
        f"Preferences: {json.dumps(prefs)}\n\n"
        f"Resume:\n{resume_text[:2000]}\n\n"
        f"Candidates:\n{json.dumps(compact)}"
    )
    result = await llm.structured(
        system=_SYSTEM, user=user, tool_name="rank_jobs", schema=_SCHEMA
    )
    by_id = {r["external_id"]: r for r in result.get("rankings", [])}
    ranked: list[RankedJob] = []
    for c in candidates:
        r = by_id.get(c.get("external_id"), {})
        ranked.append(
            RankedJob(**c, score=int(r.get("score", 0)), reason=r.get("reason", ""))
        )
    ranked.sort(key=lambda j: j.get("score", 0), reverse=True)
    return ranked
