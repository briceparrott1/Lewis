import asyncio
import logging
import time

import httpx

from lewis_api.agent.normalize import job_key
from lewis_api.agent.sources.ashby import fetch_ashby
from lewis_api.agent.sources.greenhouse import fetch_greenhouse
from lewis_api.agent.sources.seed import SeedEntry, load_seed  # noqa: F401
from lewis_api.agent.state import Job

logger = logging.getLogger(__name__)

_CACHE: dict[tuple[str, str], tuple[float, list[Job]]] = {}
_TTL = 600.0


async def _fetch_one(
    entry: SeedEntry, client: httpx.AsyncClient, timeout: float
) -> list[Job]:
    key = (entry.source, entry.board_token)
    cached = _CACHE.get(key)
    if cached and (time.monotonic() - cached[0]) < _TTL:
        return cached[1]
    fetcher = fetch_greenhouse if entry.source == "greenhouse" else fetch_ashby
    jobs = await asyncio.wait_for(fetcher(entry.board_token, client), timeout)
    for job in jobs:
        job["company"] = entry.company
        job["industry"] = entry.industry
    _CACHE[key] = (time.monotonic(), jobs)
    return jobs


async def fetch_all_boards(
    entries: list[SeedEntry],
    client: httpx.AsyncClient | None,
    *,
    concurrency: int = 40,
    timeout: float = 5.0,
) -> list[Job]:
    sem = asyncio.Semaphore(concurrency)

    async def guarded(entry: SeedEntry) -> list[Job]:
        async with sem:
            try:
                return await _fetch_one(entry, client, timeout)
            except httpx.HTTPStatusError as exc:
                if exc.response is not None and exc.response.status_code == 429:
                    logger.warning(
                        "rate limited fetching %s/%s", entry.source, entry.board_token
                    )
                else:
                    logger.info(
                        "board fetch failed for %s/%s: %s",
                        entry.source,
                        entry.board_token,
                        exc,
                    )
                return []
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "board fetch failed for %s/%s: %s",
                    entry.source,
                    entry.board_token,
                    exc,
                )
                return []  # partial-failure tolerant: skip this board

    results = await asyncio.gather(*(guarded(e) for e in entries))
    seen: set[str] = set()
    merged: list[Job] = []
    for jobs in results:
        for job in jobs:
            k = job_key(job)
            if k not in seen:
                seen.add(k)
                merged.append(job)
    return merged
