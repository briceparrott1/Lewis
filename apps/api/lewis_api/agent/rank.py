import json

from lewis_api.agent.llm import LLM
from lewis_api.agent.state import Job, RankedJob, StructuredPrefs

_VALID_SENIORITY = {"intern", "new_grad", "mid", "senior", "staff", "unknown"}

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
                    "seniority": {
                        "type": "string",
                        "enum": [
                            "intern",
                            "new_grad",
                            "mid",
                            "senior",
                            "staff",
                            "unknown",
                        ],
                    },
                },
                "required": ["external_id", "score", "reason", "seniority"],
            },
        }
    },
    "required": ["rankings"],
}

_SYSTEM = (
    "Score each candidate job 0-100 for how well it fits the user's resume and "
    "preferences. Trade off soft preferences in the order given by 'priorities' "
    "(most important first); never violate a 'required' dimension. Give a concise "
    "one-line reason per job, citing tradeoffs where relevant. Also classify each "
    "job's seniority level as one of intern, new_grad, mid, senior, or staff, based "
    "only on explicit signals in its title or description (e.g. 'Senior', 'New Grad', "
    "'Staff', years-of-experience ranges). If the title and description give no clear "
    "seniority signal, classify it as unknown rather than guessing."
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
        ext_id = c.get("external_id")
        if ext_id not in by_id:
            continue  # LLM never addressed this candidate — don't show it
        r = by_id[ext_id]
        seniority = r.get("seniority", "unknown")
        if seniority not in _VALID_SENIORITY:
            seniority = "unknown"
        ranked.append(
            RankedJob(
                **c,
                score=int(r.get("score", 0)),
                reason=r.get("reason", ""),
                seniority=seniority,
            )
        )
    ranked.sort(key=lambda j: j.get("score", 0), reverse=True)
    return ranked
