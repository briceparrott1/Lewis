import httpx

from lewis_api.agent.state import Job

_URL = "https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true"


async def fetch_ashby(org: str, client: httpx.AsyncClient) -> list[Job]:
    resp = await client.get(_URL.format(org=org))
    resp.raise_for_status()
    jobs: list[Job] = []
    for item in resp.json().get("jobs", []):
        comp = item.get("compensation") or {}
        jobs.append(
            Job(
                source="ashby",
                company=org,
                board_token=org,
                external_id=str(item["id"]),
                title=item.get("title", ""),
                location=item.get("location", ""),
                department=item.get("department"),
                url=item["jobUrl"],
                posted_at=item.get("publishedAt"),
                compensation=comp.get("summary") if isinstance(comp, dict) else None,
                description=(item.get("descriptionPlain") or "")[:2000],
            )
        )
    return jobs
