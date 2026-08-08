from lewis_api.agent.seniority import classify_relationship
from lewis_api.agent.state import RankedJob, StructuredPrefs

COMPANY_CAP = 2
ADJACENT_TIER_CAP = 3
INDUSTRY_CAP = 3


def select_results(
    ranked: list[RankedJob],
    prefs: StructuredPrefs,
    max_results: int,
) -> list[RankedJob]:
    """Greedily build the final results, honoring the per-company cap, the
    per-industry cap, and the adjacent-seniority-tier cap. `ranked` must
    already be sorted by score descending and hard-excluded via
    seniority.filter_by_seniority. An "unknown" industry (unset in the seed
    data) is unrestricted, mirroring how seniority.py treats "unknown".
    """
    user_seniority = prefs.get("seniority")
    selected: list[RankedJob] = []
    company_counts: dict[str, int] = {}
    industry_counts: dict[str, int] = {}
    adjacent_count = 0
    for job in ranked:
        if len(selected) >= max_results:
            break
        company = job.get("company", "")
        if company_counts.get(company, 0) >= COMPANY_CAP:
            continue
        industry = job.get("industry", "unknown")
        if industry != "unknown" and industry_counts.get(industry, 0) >= INDUSTRY_CAP:
            continue
        relationship = classify_relationship(
            user_seniority, job.get("seniority", "unknown")
        )
        if relationship == "adjacent_above" and adjacent_count >= ADJACENT_TIER_CAP:
            continue
        selected.append(job)
        company_counts[company] = company_counts.get(company, 0) + 1
        if industry != "unknown":
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
        if relationship == "adjacent_above":
            adjacent_count += 1
    return selected
