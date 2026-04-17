"""工作流节点占位实现。"""

from app.core.state import AgentState


def draft_plan(state: AgentState) -> AgentState:
    state.steps.append("draft_plan")
    state.notes.append(f"已规划任务：{state.task}")
    return state
