import logging
from collections.abc import AsyncIterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from lewis_api.agent.narrate import narrate_results
from lewis_api.agent.normalize import job_key
from lewis_api.agent.prefilter import prefilter
from lewis_api.agent.prefs import is_sufficient, parse_prefs
from lewis_api.agent.rank import rank_jobs
from lewis_api.agent.select_results import select_results
from lewis_api.agent.seniority import filter_by_seniority
from lewis_api.agent.state import AgentState
from lewis_api.agent.tracing import langfuse_run_config
from lewis_api.config import get_settings

logger = logging.getLogger(__name__)

CLARIFY_TEXT = (
    "To narrow this down: which locations are you targeting, or is remote OK? "
    "And what seniority (e.g. new grad, mid, senior)?"
)


def build_graph(llm, fetch_boards, seed, checkpointer):
    async def ingest(state: AgentState) -> dict:
        return {
            "prefs": state.get("prefs", {}),
            "clarified_once": state.get("clarified_once", False),
        }

    async def parse(state: AgentState) -> dict:
        get_stream_writer()(
            {"type": "status", "text": "Reading your resume and preferences…"}
        )
        prefs = await parse_prefs(
            state["new_message"],
            state.get("prefs", {}),
            state.get("resume_text", ""),
            llm,
        )
        return {"prefs": prefs}

    def route(state: AgentState) -> str:
        if is_sufficient(state["prefs"]) or state.get("clarified_once"):
            return "search"
        return "clarify"

    async def clarify(state: AgentState) -> dict:
        get_stream_writer()({"type": "clarify", "question": CLARIFY_TEXT})
        return {"clarified_once": True, "clarify_question": CLARIFY_TEXT}

    async def search(state: AgentState) -> dict:
        writer = get_stream_writer()
        writer(
            {"type": "status", "text": f"Scanning {len(seed)} companies for openings…"}
        )
        jobs = await fetch_boards(seed, None)
        served = set(state.get("served_keys", []))
        fresh = [j for j in jobs if job_key(j) not in served]
        writer({"type": "status", "text": "Filtering to your criteria…"})
        candidates = prefilter(fresh, state["prefs"])
        writer({"type": "status", "text": "Ranking matches against your profile…"})
        ranked = await rank_jobs(
            candidates, state["prefs"], state.get("resume_text", ""), llm
        )
        return {"candidates": candidates, "ranked": ranked}

    async def respond(state: AgentState) -> dict:
        writer = get_stream_writer()
        ranked = state.get("ranked", [])
        eligible = filter_by_seniority(ranked, state["prefs"])
        top = select_results(eligible, state["prefs"], get_settings().max_results)
        logger.info(
            "respond funnel: ranked=%d eligible=%d top=%d",
            len(ranked),
            len(eligible),
            len(top),
        )
        writer({"type": "status", "text": "Writing up what I found…"})
        narrative = await narrate_results(
            top,
            state["prefs"],
            state.get("resume_text", ""),
            state.get("user_name"),
            llm,
        )
        writer({"type": "narrative", "text": narrative})
        for job in top:
            writer({"type": "result", "job": job})
        return {"ranked": top}

    builder = StateGraph(AgentState)
    builder.add_node("ingest", ingest)
    builder.add_node("parse", parse)
    builder.add_node("clarify", clarify)
    builder.add_node("search", search)
    builder.add_node("respond", respond)
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "parse")
    builder.add_conditional_edges(
        "parse", route, {"clarify": "clarify", "search": "search"}
    )
    builder.add_edge("clarify", END)
    builder.add_edge("search", "respond")
    builder.add_edge("respond", END)
    return builder.compile(checkpointer=checkpointer)


async def run_agent(
    graph,
    *,
    user_id: str,
    resume_text: str,
    served_keys: list[str],
    message: str,
    thread_id: str,
    user_name: str | None = None,
) -> AsyncIterator[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    config.update(langfuse_run_config(user_id, thread_id))
    inputs = {
        "user_id": user_id,
        "resume_text": resume_text,
        "served_keys": served_keys,
        "new_message": message,
        "user_name": user_name,
    }
    shown: list[dict] = []
    async for event in graph.astream(inputs, config, stream_mode="custom"):
        if event.get("type") == "result":
            shown.append(event["job"])
        yield event
    yield {
        "type": "done",
        "count": len(shown),
        "served_keys": [job_key(j) for j in shown],
    }
