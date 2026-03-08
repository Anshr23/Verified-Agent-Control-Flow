"""
FastAPI wrapper around the verified agent.

Endpoints:
  POST /chat            -> run one turn through the agent (build_graph_v2)
  GET  /verification     -> re-run NuSMV against model_v3.smv and return
                             the parsed spec results as JSON
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.graph import build_graph_v2
from agent.schemas import AgentState
from tests.test_verification_gate import run_nusmv, parse_spec_results, MODEL_PATH

app = FastAPI(title="Verified Agent Control Flow")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in a real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

_graph = build_graph_v2().compile()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    phase: str
    final_response: str | None
    confirmed: bool
    clarify_count: int
    injection_flagged: bool


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    result = _graph.invoke(
        AgentState(user_message=req.message),
        config={"recursion_limit": 15},
    )
    return ChatResponse(
        phase=str(result["phase"]),
        final_response=result.get("final_response"),
        confirmed=result.get("confirmed", False),
        clarify_count=result.get("clarify_count", 0),
        injection_flagged=result.get("injection_flagged", False),
    )


class SpecResult(BaseModel):
    spec: str
    holds: bool


@app.get("/verification", response_model=list[SpecResult])
def verification_status():
    output = run_nusmv(MODEL_PATH)
    results = parse_spec_results(output)
    return [SpecResult(spec=spec, holds=ok) for spec, ok in results]


@app.get("/health")
def health():
    return {"status": "ok"}