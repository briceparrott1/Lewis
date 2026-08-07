from urllib.parse import urlsplit, urlunsplit

from lewis_api.agent.state import Job


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = "https"
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


def job_key(job: Job) -> str:
    return normalize_url(job["url"])
