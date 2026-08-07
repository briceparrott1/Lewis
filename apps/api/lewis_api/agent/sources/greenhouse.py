import re

import httpx

from lewis_api.agent.state import Job

_TAG = re.compile(r"<[^>]+>")
_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    import html

    return html.unescape(_TAG.sub(" ", text)).strip()


async def fetch_greenhouse(token: str, client: httpx.AsyncClient) -> list[Job]:
    resp = await client.get(_URL.format(token=token))
    resp.raise_for_status()
    jobs: list[Job] = []
    for item in resp.json().get("jobs", []):
        jobs.append(
            Job(
                source="greenhouse",
                company=token,
                board_token=token,
                external_id=str(item["id"]),
                title=item.get("title", ""),
                location=(item.get("location") or {}).get("name", ""),
                department=None,
                url=item["absolute_url"],
                posted_at=item.get("updated_at"),
                compensation=None,
                description=_strip_html(item.get("content"))[:2000],
            )
        )
    return jobs
