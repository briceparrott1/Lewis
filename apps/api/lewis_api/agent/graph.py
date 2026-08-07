from collections.abc import AsyncIterator

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from lewis_api.agent.normalize import job_key
from lewis_api.agent.prefilter import prefilter
from lewis_api.agent.prefs import is_sufficient, parse_prefs
from lewis_api.agent.rank import rank_jobs
from lewis_api.agent.state import AgentState
from lewis_api.config import get_settings

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
        writer({"type": "status", "text": f"Scanning {len(seed)} companies…"})
        jobs = await fetch_boards(seed, None)
        served = set(state.get("served_keys", []))
        fresh = [j for j in jobs if job_key(j) not in served]
        writer({"type": "status", "text": f"Ranking {len(fresh)} matches…"})
        candidates = prefilter(fresh, state["prefs"])
        ranked = await rank_jobs(
            candidates, state["prefs"], state.get("resume_text", ""), llm
        )
        return {"candidates": candidates, "ranked": ranked}

    async def respond(state: AgentState) -> dict:
        writer = get_stream_writer()
        top = state.get("ranked", [])[: get_settings().max_results]
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
) -> AsyncIterator[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    inputs = {
        "user_id": user_id,
        "resume_text": resume_text,
        "served_keys": served_keys,
        "new_message": message,
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
