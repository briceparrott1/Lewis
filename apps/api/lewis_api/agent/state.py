from typing import Literal, TypedDict


class StructuredPrefs(TypedDict, total=False):
    role_keywords: list[str]
    locations: list[str]
    remote_ok: bool | None
    seniority: Literal["intern", "new_grad", "mid", "senior", "staff"] | None
    extra: str
    required: list[str]
    priorities: list[str]


class Job(TypedDict, total=False):
    source: Literal["greenhouse", "ashby"]
    company: str
    board_token: str
    external_id: str
    title: str
    location: str
    department: str | None
    url: str
    posted_at: str | None
    compensation: str | None
    description: str


class RankedJob(Job, total=False):
    score: int
    reason: str
    seniority: Literal["intern", "new_grad", "mid", "senior", "staff", "unknown"]


class AgentState(TypedDict, total=False):
    user_id: str
    resume_text: str
    prefs: StructuredPrefs
    clarified_once: bool
    served_keys: list[str]
    new_message: str
    candidates: list[Job]
    ranked: list[RankedJob]
    clarify_question: str | None
