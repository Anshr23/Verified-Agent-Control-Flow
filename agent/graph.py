"""
LangGraph state graph for a support/ops agent.
v1 — contains an intentional control-flow flaw (see NOTE below) that
the NuSMV liveness property will catch. Fixed in v2 after verification.

LLM calls are stubbed with deterministic mock functions so the graph
is runnable/testable without API keys. Swap `mock_plan_llm` /
`mock_tool_select_llm` for a real langchain LLM call when you want it live.
"""

from langgraph.graph import StateGraph, END
from agent.schemas import AgentState, AgentPhase, ToolCall, ToolName


# ---- stubbed "LLM" logic (deterministic, for graph testing) ----

def mock_plan_llm(user_message: str) -> str:
    if "refund" in user_message.lower():
        return "Plan: verify order, then issue refund."
    if "delete" in user_message.lower():
        return "Plan: confirm identity, then delete account."
    if "record" in user_message.lower() or "history" in user_message.lower():
        return "Plan: look up requested info."
    return "Plan: unclear, request is ambiguous."   # <-- new fallback


def mock_tool_select_llm(plan_summary: str) -> ToolCall | None:
    if "refund" in plan_summary.lower():
        return ToolCall(name=ToolName.ISSUE_REFUND, args={"amount": 100})
    if "delete" in plan_summary.lower():
        return ToolCall(name=ToolName.DELETE_ACCOUNT, args={})
    if "look up" in plan_summary.lower():
        return ToolCall(name=ToolName.SEARCH_RECORDS, args={})
    return None  # ambiguous -> needs clarification


# ---- nodes ----

def intake_node(state: AgentState) -> dict:
    return {"phase": AgentPhase.PLAN}


def plan_node(state: AgentState) -> dict:
    summary = mock_plan_llm(state.user_message)
    return {"phase": AgentPhase.TOOL_SELECT, "plan_summary": summary}


def tool_select_node(state: AgentState) -> dict:
    call = mock_tool_select_llm(state.plan_summary or "")
    if call is None:
        return {"phase": AgentPhase.CLARIFY}
    if call.is_destructive:
        return {"phase": AgentPhase.HUMAN_CONFIRM, "pending_tool_call": call}
    return {"phase": AgentPhase.EXECUTE, "pending_tool_call": call}


def clarify_node(state: AgentState) -> dict:
    # NOTE (INTENTIONAL FLAW, v1):
    # clarify_count is incremented here, but nothing ever routes to a
    # terminal/give-up state when max_clarify is hit — the routing
    # function below always sends control back to `plan`. If the mock
    # LLM keeps returning an ambiguous plan, this loop never exits.
    # -> NuSMV liveness property L1 ("every conversation eventually
    #    reaches a terminal state") will fail on this model.
    return {"phase": AgentPhase.PLAN, "clarify_count": state.clarify_count + 1}


def human_confirm_node(state: AgentState) -> dict:
    # Simulates a human approving. In v1, rejection isn't modeled at all
    # (always confirms) — acceptable for now, not the flaw we're testing.
    return {"phase": AgentPhase.EXECUTE, "confirmed": True}


def execute_node(state: AgentState) -> dict:
    call = state.pending_tool_call
    result = f"executed {call.name if call else 'nothing'}"
    return {"phase": AgentPhase.RESPOND, "execution_result": result}


def respond_node(state: AgentState) -> dict:
    return {"phase": AgentPhase.RESPOND, "final_response": "Done."}


# ---- routing ----

def route_from_tool_select(state: AgentState) -> str:
    if state.phase == AgentPhase.CLARIFY:
        return "clarify"
    if state.phase == AgentPhase.HUMAN_CONFIRM:
        return "human_confirm"
    return "execute"


def route_from_clarify(state: AgentState) -> str:
    # FLAW: no check against state.max_clarify here.
    return "plan"


def build_graph_v1() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("intake", intake_node)
    g.add_node("plan", plan_node)
    g.add_node("tool_select", tool_select_node)
    g.add_node("clarify", clarify_node)
    g.add_node("human_confirm", human_confirm_node)
    g.add_node("execute", execute_node)
    g.add_node("respond", respond_node)

    g.set_entry_point("intake")
    g.add_edge("intake", "plan")
    g.add_edge("plan", "tool_select")
    g.add_conditional_edges("tool_select", route_from_tool_select, {
        "clarify": "clarify",
        "human_confirm": "human_confirm",
        "execute": "execute",
    })
    g.add_conditional_edges("clarify", route_from_clarify, {"plan": "plan"})
    g.add_edge("human_confirm", "execute")
    g.add_edge("execute", "respond")
    g.add_edge("respond", END)

    return g


if __name__ == "__main__":
    graph = build_graph_v1().compile()
    result = graph.invoke(AgentState(user_message="I want a refund"))
    print(result)