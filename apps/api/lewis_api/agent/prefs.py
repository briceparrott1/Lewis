from lewis_api.agent.llm import LLM
from lewis_api.agent.state import StructuredPrefs

_SCHEMA = {
    "type": "object",
    "properties": {
        "role_keywords": {"type": "array", "items": {"type": "string"}},
        "locations": {"type": "array", "items": {"type": "string"}},
        "remote_ok": {"type": ["boolean", "null"]},
        "seniority": {
            "type": ["string", "null"],
            "enum": ["intern", "new_grad", "mid", "senior", "staff", None],
        },
        "extra": {"type": "string"},
        "required": {"type": "array", "items": {"type": "string"}},
        "priorities": {"type": "array", "items": {"type": "string"}},
    },
}

_SYSTEM = (
    "Extract structured job-search preferences from the user's message. "
    "role_keywords: job title/role terms. locations: cities/regions. "
    "remote_ok: true if remote acceptable. seniority: one of intern/new_grad/mid/"
    "senior/staff or null. required: dimensions that are dealbreakers "
    "(subset of ['role','location']). priorities: dimensions ordered most-important "
    "first. For locations, use full names as they appear in job postings "
    "(e.g. 'San Francisco', not 'SF'). Only include fields the user actually expressed."
)


async def parse_prefs(
    message: str, prior: StructuredPrefs, resume_text: str, llm: LLM
) -> StructuredPrefs:
    extracted = await llm.structured(
        system=_SYSTEM,
        user=f"Message: {message}\n\nResume (for context):\n{resume_text[:2000]}",
        tool_name="record_preferences",
        schema=_SCHEMA,
    )
    merged: StructuredPrefs = dict(prior)  # type: ignore[assignment]
    for key, value in extracted.items():
        if value in (None, [], ""):
            continue
        merged[key] = value  # type: ignore[literal-required]
    return merged


def is_sufficient(prefs: StructuredPrefs) -> bool:
    has_role = bool(prefs.get("role_keywords"))
    has_place = bool(prefs.get("locations")) or prefs.get("remote_ok") is True
    return has_role and has_place
