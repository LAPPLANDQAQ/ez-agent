"""最小图构建占位实现。"""

from app.core.nodes import draft_plan
from app.core.state import AgentState


def run_graph(task: str) -> AgentState:
    state = AgentState(task=task)
    return draft_plan(state)
