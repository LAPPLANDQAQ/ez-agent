"""智能体工作流的状态容器。"""

from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentState:
    task: str
    steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
