from lewis_api.agent.state import Job, StructuredPrefs


def _kw_hit(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keywords)


def _weight(dimension: str, priorities: list[str]) -> float:
    if dimension in priorities:
        return float(len(priorities) - priorities.index(dimension))
    return 1.0


def _score(job: Job, prefs: StructuredPrefs) -> float:
    priorities = prefs.get("priorities", [])
    score = 0.0
    roles = prefs.get("role_keywords", [])
    if roles and _kw_hit(job.get("title", ""), roles):
        score += 5.0 * _weight("role", priorities)
    locations = prefs.get("locations", [])
    if locations and _kw_hit(job.get("location", ""), locations):
        score += 2.0 * _weight("location", priorities)
    if prefs.get("remote_ok") and "remote" in job.get("location", "").lower():
        score += 2.0 * _weight("location", priorities)
    return score


def _passes_required(job: Job, prefs: StructuredPrefs) -> bool:
    required = prefs.get("required", [])
    if "role" in required:
        roles = prefs.get("role_keywords", [])
        if roles and not _kw_hit(job.get("title", ""), roles):
            return False
    if "location" in required:
        locs = prefs.get("locations", [])
        remote_ok = prefs.get("remote_ok")
        loc_text = job.get("location", "").lower()
        loc_hit = locs and _kw_hit(loc_text, locs)
        remote_hit = remote_ok and "remote" in loc_text
        if not (loc_hit or remote_hit):
            return False
    return True


def prefilter(jobs: list[Job], prefs: StructuredPrefs, *, cap: int = 50) -> list[Job]:
    scored: list[tuple[float, Job]] = []
    for job in jobs:
        if not _passes_required(job, prefs):
            continue
        s = _score(job, prefs)
        if s <= 0:
            continue
        scored.append((s, job))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [job for _, job in scored[:cap]]
