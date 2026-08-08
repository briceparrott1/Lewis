from lewis_api.agent.llm import LLM
from lewis_api.agent.prefs import missing_fields
from lewis_api.agent.state import StructuredPrefs

CLARIFY_TEXT = (
    "To narrow this down: which locations are you targeting, or is remote OK? "
    "And what seniority (e.g. new grad, mid, senior)?"
)

_SYSTEM = (
    "You are Lewis, a friendly job-search assistant chatting with a user in a "
    "job-search app. They haven't given you enough to search yet. Briefly "
    "acknowledge what they just said — even if it's just a greeting or small "
    "talk unrelated to a job search — then ask a short, natural question "
    "covering what's still missing. 1-2 sentences, conversational, no bullet "
    "points, no markdown."
)


async def generate_clarify_reply(
    user_message: str, prefs: StructuredPrefs, llm: LLM
) -> str:
    missing = missing_fields(prefs)
    user = (
        f"User just said: {user_message!r}\n\n"
        f"Preferences gathered so far: {prefs}\n\n"
        f"Still need to ask about: {', '.join(missing)}"
    )
    try:
        return await llm.complete(system=_SYSTEM, user=user)
    except Exception:  # noqa: BLE001
        return CLARIFY_TEXT
