# Verified Agent Control Flow

**Stack:** LangGraph, LangChain, Pydantic, Guardrails, Langfuse, FastAPI, pytest, NuSMV 2.6.x
**Method:** Symbolic Model Checking (BDD-based LTL) applied to an AI agent's control-flow graph
**Companion project:** [Formal Verification of a Finite-State Login Authentication Protocol](https://github.com/Anshr23/formal-auth-protocol-verification) — same methodology (NuSMV/LTL), applied here to a production AI system instead of an authentication FSM.

---

## Abstract

This project takes the formal verification methodology from a DRDO internship — NuSMV-based LTL/CTL model checking of a finite-state system — and applies it to a LangGraph AI agent's control flow. The agent (a support/ops assistant with tools including refunds and account deletion) is modeled as a finite-state transition system extracted directly from its actual graph definition, not a hand-drawn diagram. Four properties are verified: two safety properties (no destructive action without human confirmation; terminated conversations stay terminated) and two liveness properties (every conversation eventually terminates; confirmed destructive requests eventually execute).

The initial model (v1) fails a liveness property, exposing a real bug in the agent — an unbounded clarification loop that also crashes at runtime via LangGraph's recursion limit. A first fix (v2) repairs the loop but introduces a new failure in a safety property, traced to a modeling artifact (an environment variable re-randomized on every step instead of only at its actual decision point) rather than a real agent flaw. A second refinement (v3) fixes the modeling issue; all four properties hold. The real agent code is then updated to match the verified model, and the check is wired into a pytest gate that shells out to NuSMV, so a future code change that breaks a verified property fails CI automatically.

All claims are strictly limited to the formal model. No real-world security guarantees are asserted beyond what NuSMV's model checking establishes.

---

## Repository Structure

```
verified-agent-control-flow/
├── agent/
│   ├── schemas.py              # Pydantic state, tool, and phase definitions
│   ├── graph.py                 # LangGraph definitions: v1 (buggy) and v2 (fixed)
│   └── guardrails.py            # injection scanning + confirmation-source guard
├── verification/
│   ├── extractor.py             # introspects graph.py -> generates .smv skeleton
│   ├── model_v1.smv             # first model (L1 liveness fails)
│   ├── model_v2.smv             # partial fix (S1 safety fails - modeling artifact)
│   ├── model_v3.smv             # refined model (all 4 properties pass)
│   ├── model_broken_reference.smv  # deliberately-reintroduced bug, used to validate the CI gate itself
│   └── properties.smv           # LTL specifications (S1, S2, L1, L2)
├── api/
│   └── app.py                   # FastAPI: /chat, /verification, /health
├── dashboard/
│   └── index.html                # live results view: spec status + agent demo
├── tests/
│   ├── test_nodes.py             # unit tests for node/routing logic
│   └── test_verification_gate.py # CI gate: runs NuSMV, fails build on any false spec
├── pytest.ini
├── requirements.txt
└── README.md
```

---

## System Model Overview

- **States:** `{INTAKE, PLAN, TOOL_SELECT, CLARIFY, HUMAN_CONFIRM, EXECUTE, RESPOND, TERMINAL}`
- **Initial state:** `INTAKE`
- **Environment:** Nondeterministic, decided at the actual branch point (`PLAN`, in v3) — `input_ambiguous`, `selected_destructive`
- **Bounded retry:** `clarify_count` (0..3), gives up gracefully at the limit (v2+)

### State Variables

| Variable | Description |
|---|---|
| `state` | Current agent phase (FSM location) |
| `input_ambiguous` | Nondeterministic: did tool selection resolve? |
| `selected_destructive` | Nondeterministic: is the chosen tool destructive (refund/delete)? |
| `confirmed` | Set only by the human-confirm step |
| `clarify_count` | Bounded retry counter (0..3) |

---

## Transition Summary (v3, matches `agent/graph.py`'s `build_graph_v2`)

- INTAKE → PLAN
- PLAN → TOOL_SELECT
- TOOL_SELECT → CLARIFY (if ambiguous)
- TOOL_SELECT → HUMAN_CONFIRM (if destructive)
- TOOL_SELECT → EXECUTE (if non-destructive, resolved)
- CLARIFY → PLAN (retry, if `clarify_count < 3`)
- CLARIFY → RESPOND (give up, if `clarify_count = 3`)
- HUMAN_CONFIRM → EXECUTE
- EXECUTE → RESPOND
- RESPOND → TERMINAL (absorbing)

---

## Properties Verified

### Safety

**S1 — No Unconfirmed Destructive Execution**

G((state = EXECUTE ∧ selected_destructive) → confirmed)


**S2 — Termination Permanence**

G(state = TERMINAL → G(state = TERMINAL))


### Liveness

**L1 — Every Conversation Eventually Terminates**

G(F(state = TERMINAL))

Fails in v1 (unbounded clarify loop). Passes from v2 onward.

**L2 — Confirmed Destructive Requests Eventually Execute**

G(state = HUMAN_CONFIRM → F(state = EXECUTE))


---

## Verification Workflow

1. Build LangGraph agent (`agent/graph.py`).
2. Extract FSM skeleton from the actual graph definition (`verification/extractor.py`).
3. Hand-complete branch conditions from routing functions → `.smv` model.
4. Specify LTL safety and liveness properties.
5. Run NuSMV — v1 fails L1 (real bug: unbounded retry loop).
6. Analyze counterexample (lasso trace), fix the graph logic → v2.
7. Re-run — v2 fails S1 (modeling artifact: environment re-randomized every step, not just at the decision point).
8. Fix the model's randomization timing → v3.
9. Re-run — all 4 properties hold.
10. Update real agent code (`build_graph_v2`) to match the verified logic.
11. Wire verification into `tests/test_verification_gate.py`, run via pytest, validated by deliberately reintroducing the v1 bug and confirming the gate fails (`model_broken_reference.smv`).

---

## Running It

```bash
# unit tests
pytest tests/test_nodes.py -v

# verification gate (requires NuSMV on PATH)
pytest tests/test_verification_gate.py -v

# run NuSMV directly
NuSMV verification/model_v3.smv

# API
uvicorn api.app:app --reload --port 8000

# dashboard (with API running)
open dashboard/index.html
```

---

## Assumptions and Abstractions

1. Single-session, single-turn-at-a-time (no concurrency).
2. Tool selection resolution and destructiveness abstracted as booleans.
3. LLM calls stubbed deterministically for graph-structure testing (no live model dependency in the formal model or unit tests).
4. Human confirmation always succeeds when reached (rejection path not modeled).
5. `.smv` model is a manually-completed extension of an auto-extracted skeleton, not a fully automatic translation — branch conditions are filled in by hand from the routing functions' actual logic.
6. Results apply only to this formal model of the control-flow graph, not to LLM output correctness, tool implementation correctness, or the guardrail's completeness against novel injection phrasing.

---

## Limitations

- No verification of LLM output content — only of the control-flow graph's structural properties.
- Guardrail injection detection is pattern-based (regex), not exhaustive.
- No concurrency, timing, or multi-user session modeling.
- Extractor produces a topology skeleton; branch conditions are completed manually, not automatically derived from `graph.py`'s routing function source.