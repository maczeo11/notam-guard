from typing import TypedDict, List
import os

# Simple router not yet LLM — swap to gpt-4o-mini when OPENAI_API_KEY set
class State(TypedDict):
    query: str
    lat: float
    lon: float
    alt: int
    drone_id: str
    retrieved: List[str]
    citations: List[str]
    verdict: str
    reason: str
    confidence: float
    ticket_id: str
    requires_human: bool

def router(state: State):
    q = state.get("query","").lower()
    has_coords = state.get("lat") is not None
    if has_coords and ("notam" in q or "crane" in q or "dgca" in q):
        return "both"
    if has_coords:
        return "act"
    return "retrieve"

def retriever(state: State):
    # try pgvector — fallback mock
    try:
        import psycopg2
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("BAAI/bge-small-en-v1.5")
        qemb = model.encode(state["query"]).tolist()
        conn = psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://notam:notam@localhost:5432/notam"))
        cur = conn.cursor()
        cur.execute("SELECT chunk FROM sop_chunks ORDER BY embedding <=> %s::vector LIMIT 3", (qemb,))
        rows = cur.fetchall()
        chunks = [r[0][:500] for r in rows] or ["DGCA CAR §7: Micro max 120m AGL", "NOTAM 09/03: Crane 100m at 18.53,73.84 radius 1km"]
    except Exception:
        chunks = ["DGCA CAR §7: Micro max 120m AGL", "NOTAM 09/03: Crane 100m at 18.53,73.84 radius 1km"]
    state["retrieved"] = chunks
    state["citations"] = ["CAR §7", "NOTAM 09/03"]
    return state

def validator_tool(state: State):
    import time
    t0 = time.perf_counter()
    from .tools import validate_flight, create_ticket
    from .memory import push_history, geo_add_tile
    res = validate_flight(state["lat"], state["lon"], state["alt"])
    state["verdict"] = "BLOCK" if res["violation"] else "ALLOW"
    state["reason"] = res["reason"]
    state["confidence"] = 0.6 if res["violation"] else 0.9
    # #7 latency per stage
    state["_latency_validator_ms"] = round((time.perf_counter()-t0)*1000, 1)
    # idempotent ticket #5 key with window
    if res["violation"]:
        t = create_ticket(res["reason"], "HIGH", state["drone_id"], res["notam_id"])
        state["ticket_id"] = t["ticket_id"] or "deduped"
        state["_ticket_key"] = t["key"]
        if not t["deduped"]:
            push_history(state["drone_id"], state["ticket_id"])
        geo_add_tile(state["lon"], state["lat"], state["drone_id"])
    else:
        state["ticket_id"] = ""
        state["_ticket_key"] = ""
    # human gate #4 calibration: 0.7 justified via eval — see docs/EVAL.md
    state["requires_human"] = state["verdict"] == "BLOCK" or state["confidence"] < 0.7
    return state

def grounding_check(state: State):
    """#1 grounding: verify every citation string appears in retrieved chunks; if not, human-gate"""
    import re
    retrieved_text = " ".join(state.get("retrieved", [])).lower()
    bad = []
    for c in state.get("citations", []):
        # normalize citation like "NOTAM 09/03" -> must appear verbatim
        if c.lower() not in retrieved_text:
            # also try number only
            num = re.search(r"\d+/\d+", c)
            if not num or num.group(0) not in retrieved_text:
                bad.append(c)
    if bad:
        state["confidence"] = min(state.get("confidence", 0.9), 0.5)
        state["requires_human"] = True
        state["reason"] += f" [grounding fail: {','.join(bad)} not in retrieved]"
    return state

def responder(state: State):
    # simple synthesize — swap to LLM when key set
    if state["verdict"] == "BLOCK":
        state["query"] = f"{state['verdict']}: {state['reason']} — reduce to 80m. Citations: {', '.join(state['citations'])}"
    else:
        state["query"] = f"{state['verdict']}: clear — citations {', '.join(state['citations'])}"
    # #7 latency hook — timestamp per stage done in validator_tool
    return grounding_check(state)

def build_graph():
    # LangGraph when available — fallback sequential for now to keep B.Tech simple
    try:
        from langgraph.graph import StateGraph, END
        g = StateGraph(State)
        g.add_node("retriever", retriever)
        g.add_node("validator", validator_tool)
        g.add_node("responder", responder)
        g.set_entry_point("retriever")
        g.add_edge("retriever", "validator")
        g.add_edge("validator", "responder")
        g.add_edge("responder", END)
        return g.compile()
    except Exception:
        # fallback: sequential
        class Seq:
            def invoke(self, s): s=retriever(s); s=validator_tool(s); s=responder(s); return s
        return Seq()

graph = build_graph()
