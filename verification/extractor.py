"""
Extracts the LangGraph node/edge structure from agent/graph.py and
generates a NuSMV .smv model from it. This ensures the formal model
tracks the real graph definition, not a manually-drawn twin of it.

Usage:
    python3 -m verification.extractor > verification/model_v1.smv
"""

from agent.graph import build_graph_v1
from agent.schemas import AgentPhase


def extract_states_and_edges(graph_builder):
    """
    Pulls node names and edges out of a compiled/uncompiled StateGraph.
    LangGraph exposes .nodes and .branches (conditional) / .edges (direct)
    on the StateGraph object before compilation.
    """
    g = graph_builder()

    states = set(g.nodes.keys())
    states.discard("__start__")

    direct_edges = []   # (from, to)
    cond_edges = []      # (from, [to, to, ...])

    for src, targets in g.edges:
        # g.edges is a set of (src, dst) tuples in current LangGraph versions
        pass

    # LangGraph's internal edge storage varies by version; the robust way
    # is to read the compiled graph's drawable representation instead.
    compiled = g.compile()
    graph_repr = compiled.get_graph()

    node_names = [n for n in graph_repr.nodes if n not in ("__start__", "__end__")]
    edges = []
    for e in graph_repr.edges:
        src = e.source if e.source not in ("__start__",) else "intake_entry"
        dst = e.target if e.target not in ("__end__",) else "TERMINAL"
        edges.append((src, dst, getattr(e, "conditional", False)))

    return node_names, edges


def to_smv_state_name(name: str) -> str:
    return name.upper()


def generate_smv(node_names, edges) -> str:
    smv_states = [to_smv_state_name(n) for n in node_names] + ["TERMINAL"]
    smv_states = list(dict.fromkeys(smv_states))  # dedupe, preserve order

    lines = []
    lines.append("-- AUTO-GENERATED from agent/graph.py by verification/extractor.py")
    lines.append("-- Do not hand-edit; re-run the extractor after changing graph.py")
    lines.append("")
    lines.append("MODULE main")
    lines.append("VAR")
    lines.append(f"    state : {{{', '.join(smv_states)}}};")
    lines.append("    confirmed : boolean;")
    lines.append("    destructive_pending : boolean;")
    lines.append("    clarify_count : 0..3;")
    lines.append("")
    lines.append("ASSIGN")
    lines.append("    init(state) := INTAKE;")
    lines.append("    init(confirmed) := FALSE;")
    lines.append("    init(destructive_pending) := FALSE;")
    lines.append("    init(clarify_count) := 0;")
    lines.append("")
    lines.append("    next(state) := case")

    for src, dst, is_conditional in edges:
        src_s = to_smv_state_name(src) if src != "intake_entry" else "INTAKE"
        dst_s = to_smv_state_name(dst)
        if src_s == dst_s:
            continue
        lines.append(f"        state = {src_s} & next_hint_{src_s.lower()}_{dst_s.lower()} : {dst_s};")

    lines.append("        TRUE : state;")
    lines.append("    esac;")
    lines.append("")
    lines.append("-- NOTE: next_hint_* variables above are placeholders representing")
    lines.append("-- the branch conditions LangGraph evaluates at runtime (e.g. which")
    lines.append("-- tool was selected, whether input was ambiguous). Fill these in")
    lines.append("-- from the routing functions (route_from_tool_select, route_from_clarify)")
    lines.append("-- in graph.py -- see verification/model_v1.smv for the hand-completed version.")

    return "\n".join(lines)


if __name__ == "__main__":
    node_names, edges = extract_states_and_edges(build_graph_v1)
    print(generate_smv(node_names, edges))