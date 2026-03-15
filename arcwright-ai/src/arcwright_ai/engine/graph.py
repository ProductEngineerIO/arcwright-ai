"""Engine graph — LangGraph StateGraph construction and compilation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

from arcwright_ai.engine.nodes import (
    agent_dispatch_node,
    budget_check_node,
    commit_node,
    finalize_node,
    preflight_node,
    route_budget_check,
    route_validation,
    validate_node,
)
from arcwright_ai.engine.state import StoryState

__all__: list[str] = [
    "build_story_graph",
]


def build_story_graph() -> CompiledStateGraph[StoryState, Any, Any, Any]:
    """Build and compile the LangGraph StateGraph for single-story execution.

    Constructs a graph with six nodes (preflight, budget_check, agent_dispatch,
    validate, commit, finalize) and conditional routing based on budget limits
    and validation outcomes. All terminal paths route through finalize_node
    before END so that run-level summaries are always written.

    Graph shape::

        START → preflight → budget_check →(ok)→ agent_dispatch → validate →(success)→ commit → finalize → END
                                         ↓(exceeded)→ finalize → END        ↓(retry)→ budget_check
                                                                             ↓(escalated)→ finalize → END

    Returns:
        A compiled LangGraph ``CompiledStateGraph`` ready for invocation via
        ``await graph.ainvoke(initial_state)``.
    """
    graph: StateGraph[StoryState, Any, Any, Any] = StateGraph(StoryState)

    graph.add_node("preflight", preflight_node)
    graph.add_node("budget_check", budget_check_node)
    graph.add_node("agent_dispatch", agent_dispatch_node)
    graph.add_node("validate", validate_node)
    graph.add_node("commit", commit_node)
    graph.add_node("finalize", finalize_node)

    graph.add_edge(START, "preflight")
    graph.add_edge("preflight", "budget_check")
    graph.add_conditional_edges(
        "budget_check",
        route_budget_check,
        {"ok": "agent_dispatch", "exceeded": "finalize"},
    )
    graph.add_edge("agent_dispatch", "validate")
    graph.add_conditional_edges(
        "validate",
        route_validation,
        {"success": "commit", "retry": "budget_check", "escalated": "finalize"},
    )
    graph.add_edge("commit", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
