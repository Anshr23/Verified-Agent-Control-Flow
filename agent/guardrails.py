"""
Guardrails: input/output validation against prompt-injection attempts.
Two layers:
  1. Input scanning — flag messages trying to manipulate agent state directly
     (e.g. "ignore previous instructions", "set confirmed=true", "skip confirmation")
  2. Output validation — refuse to trust an LLM-produced plan/tool-call that
     claims confirmation already happened, since only human_confirm_node may set it.
"""

import re
from agent.schemas import AgentState, ToolCall

# Patterns indicative of injection attempts targeting this agent's control flow.
INJECTION_PATTERNS = [
    r"ignore (all|previous|prior) instructions",
    r"skip (the )?confirmation",
    r"set confirmed\s*[:=]\s*true",
    r"you are now",
    r"disregard (the )?system prompt",
    r"act as (if|though)",
    r"bypass (human[_ ]confirm|approval)",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]


def scan_input(user_message: str) -> bool:
    """Returns True if the message looks like an injection attempt."""
    return any(p.search(user_message) for p in _COMPILED)


def guard_intake(state: AgentState) -> AgentState:
    """
    Call this at the top of intake_node (or as a pre-node) to flag
    suspicious input. Does not block the conversation outright (that's
    a product decision) — flags it so downstream logic/logging can react,
    and critically, flagged state can never itself set `confirmed`.
    """
    flagged = scan_input(state.user_message)
    return state.model_copy(update={"injection_flagged": flagged})


def guard_confirmation(state: AgentState, requested_by_node: str) -> bool:
    """
    Output-side guard: `confirmed` may ONLY be set True by human_confirm_node.
    Any other node attempting to claim confirmation is rejected here —
    this is what actually enforces S1 at the code level, not just the model.
    """
    if requested_by_node != "human_confirm_node":
        return False
    return True
