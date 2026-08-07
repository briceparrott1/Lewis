from lewis_api.agent.state import RankedJob, StructuredPrefs

LADDER = ["intern", "new_grad", "mid", "senior", "staff"]


def _normalize(value: str) -> str:
    """Normalize formatting variance (case, whitespace, hyphens) before a
    LADDER lookup. Does not coerce made-up values into real ladder entries."""
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def classify_relationship(user_seniority: str | None, job_seniority: str) -> str:
    """Classify a job's seniority relative to the user's stated level.

    Returns "exact", "adjacent_above", "exclude", or "unrestricted".
    "unrestricted" covers both an unset user preference and an
    unclassifiable ("unknown") job -- neither case has enough signal to
    filter or cap on.
    """
    if not user_seniority or job_seniority == "unknown":
        return "unrestricted"
    user_seniority = _normalize(user_seniority)
    job_seniority = _normalize(job_seniority)
    if job_seniority not in LADDER or user_seniority not in LADDER:
        return "unrestricted"
    diff = LADDER.index(job_seniority) - LADDER.index(user_seniority)
    if diff == 0:
        return "exact"
    if diff == 1:
        return "adjacent_above"
    return "exclude"


def filter_by_seniority(
    ranked: list[RankedJob], prefs: StructuredPrefs
) -> list[RankedJob]:
    """Drop jobs one tier below, or 2+ tiers away, from the user's seniority."""
    user_seniority = prefs.get("seniority")
    return [
        job
        for job in ranked
        if classify_relationship(user_seniority, job.get("seniority", "unknown"))
        != "exclude"
    ]
