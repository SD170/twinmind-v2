from langgraph.graph import END, START, StateGraph

from app.core.fact_policy import should_verify_factcheck
from app.config import get_settings
from app.graph.nodes.finalize import finalize_node
from app.graph.nodes.rank_and_draft import rank_and_draft_node
from app.graph.nodes.verify_factcheck import verify_factcheck_node
from app.graph.state import WorkflowState


def _route_after_rank(state: WorkflowState) -> str:
    req = state["request"]
    rank_output = state["rank_output"]
    settings = get_settings()
    return (
        "verify_factcheck"
        if should_verify_factcheck(rank_output, req.source_policy, settings.fact_check_score_threshold)
        else "finalize"
    )


def build_live_suggestions_graph():
    graph = StateGraph(WorkflowState)
    graph.add_node("rank_and_draft", rank_and_draft_node)
    graph.add_node("verify_factcheck", verify_factcheck_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "rank_and_draft")
    graph.add_conditional_edges("rank_and_draft", _route_after_rank)
    graph.add_edge("verify_factcheck", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


live_suggestions_graph = build_live_suggestions_graph()
