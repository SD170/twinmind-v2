import time

from app.core.state_builder import build_batch_state
from app.graph.state import WorkflowState


def build_state_node(state: WorkflowState) -> WorkflowState:
    started = time.perf_counter()
    req = state["request"]
    batch_state = build_batch_state(req)
    elapsed = int((time.perf_counter() - started) * 1000)
    timings = state.get("timings", {})
    timings["state_ms"] = elapsed
    return {"batch_state": batch_state, "timings": timings}
