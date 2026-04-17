from app.core.graph import run_graph


def test_run_graph_adds_plan_step() -> None:
    state = run_graph("创建项目骨架")
    assert state.steps == ["draft_plan"]
