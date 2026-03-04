"""
Pydantic schemas for agent state and tool I/O.
These are the types that flow through the LangGraph nodes — they're also
what the extractor (Step 4) will introspect to help build the .smv model.
"""

from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class AgentPhase(str, Enum):
    """Mirrors the FSM control states — one-to-one with NuSMV states later."""
    INTAKE = "intake"
    PLAN = "plan"
    TOOL_SELECT = "tool_select"
    HUMAN_CONFIRM = "human_confirm"
    EXECUTE = "execute"
    RESPOND = "respond"
    CLARIFY = "clarify"


class ToolName(str, Enum):
    SEARCH_RECORDS = "search_records"
    ISSUE_REFUND = "issue_refund"
    DELETE_ACCOUNT = "delete_account"
    SEND_EMAIL = "send_email"


DESTRUCTIVE_TOOLS = {ToolName.ISSUE_REFUND, ToolName.DELETE_ACCOUNT}


class ToolCall(BaseModel):
    name: ToolName
    args: dict = Field(default_factory=dict)

    @property
    def is_destructive(self) -> bool:
        return self.name in DESTRUCTIVE_TOOLS


class AgentState(BaseModel):
    """
    The full state object passed between LangGraph nodes.
    `phase` is the FSM control variable — the thing the extractor
    turns into NuSMV's `state` variable.
    """
    phase: AgentPhase = AgentPhase.INTAKE
    user_message: str = ""
    plan_summary: Optional[str] = None
    pending_tool_call: Optional[ToolCall] = None
    confirmed: bool = False
    clarify_count: int = 0
    max_clarify: int = 3
    execution_result: Optional[str] = None
    final_response: Optional[str] = None
    injection_flagged: bool = False

    class Config:
        use_enum_values = True


class NodeResult(BaseModel):
    """What each node returns — next phase + state patch."""
    next_phase: AgentPhase
    state_patch: dict = Field(default_factory=dict)